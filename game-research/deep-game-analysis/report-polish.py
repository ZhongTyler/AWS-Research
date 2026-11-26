"""Offline Research adapter for copy-polish. No transport or automatic adoption."""
import argparse
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from lxml import etree, html

# Optional external executor. Importing this adapter does not load a private workspace.
import os
tool = None

def load_executor():
    global tool
    if tool is not None:
        return tool
    selected = os.environ.get('AWS_RESEARCH_COPY_POLISH_DIR')
    if not selected:
        raise ValueError('optional_executor_not_configured: set AWS_RESEARCH_COPY_POLISH_DIR to a reviewed local copy-polish directory; basic research remains available')
    directory = Path(selected).expanduser().resolve()
    entry = directory / 'run.py'
    if not entry.is_file():
        raise ValueError('optional_executor_missing_run_py')
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location('report_copy_polish', entry)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    for name in ('report_payload', 'prepare_edit_request', 'report_revision'):
        if not callable(getattr(tool, name, None)):
            tool = None
            raise ValueError('incompatible_optional_executor:' + name)
    return tool


BRIEF = ('audience', 'reader_outcome', 'report_question', 'chapter_roles',
         'comprehension_problems', 'factual_boundaries', 'allowed_moves', 'presentation')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare(report, config, output):
    load_executor()
    report, output = report.resolve(), output.resolve()
    cfg = load(config)
    brief = cfg['brief']
    if any(not brief.get(k) for k in BRIEF):
        raise ValueError('incomplete_editorial_brief')
    study = load(report / 'study.json')
    roles = brief['chapter_roles']
    if set(roles) != {s['id'] for s in study['sections']}:
        raise ValueError('brief_must_cover_all_chapters')
    context_fields = {k: v for k, v in brief.items() if k != 'chapter_roles' or not cfg.get('sections')}
    context = '\n'.join(k + ': ' + (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                        for k, v in context_fields.items())
    if len(context) > 1000:
        raise ValueError('editorial_context_exceeds_native_1000_character_limit; use concise brief or natural chapters')
    source = deepcopy(study)
    metadata = {k: source.pop(k) for k in ('unit_context', 'explanation_bindings', 'expression_plan') if k in source}
    for section in source['sections']:
        if 'explanation_targets' in section:
            metadata['section:' + section['id']] = section.pop('explanation_targets')
    versions = {p: digest(report / p) for p in ('study.json', 'reader/index.html')}
    if (report / 'manifest.json').is_file():
        versions['manifest.json'] = digest(report / 'manifest.json')
    tree = html.fromstring((report / 'reader/index.html').read_bytes(),
                           parser=html.HTMLParser(huge_tree=True, no_network=True))
    if (report / 'reader/navigation.json').is_file():
        versions['reader/navigation.json'] = digest(report / 'reader/navigation.json')
        nav = load(report / 'reader/navigation.json')
        route_prefix = ['nav', 'routes']
    else:
        embedded = tree.xpath('//script[@type="application/json" and @id="rn-routes"]')
        if len(embedded) != 1:
            raise ValueError('missing_navigation_source_or_embedded_routes')
        routes = json.loads(embedded[0].text)
        if not isinstance(routes, list):
            raise ValueError('embedded_routes_must_be_array')
        nav = dict(routes=routes)
        route_prefix = ['json', 'rn-routes']
    surfaces, mapping, component_surfaces = {}, {}, {}

    def add(text, kind, location, explanation, group=None):
        if not isinstance(text, str) or not text.strip():
            return
        key = 'surface-' + str(len(surfaces) + 1)
        surfaces[key] = dict(kind=kind, text=text, context=explanation,
                             source_revision=hashlib.sha256(text.encode()).hexdigest())
        mapping[key] = location
        if group:
            component_surfaces.setdefault(group, []).append(key)

    if 'title' in nav:
        add(nav['title'], 'navigation', ['nav', 'title'], '报告导航标题')
    for i, route in enumerate(nav['routes']):
        for field in ('name', 'intro'):
            location = route_prefix + ([i, field] if route_prefix[0] == 'nav' else [[i, field]])
            add(route[field], 'navigation', location, '领域名称或阅读总结')
        for j, step in enumerate(route['steps']):
            for field in ('title', 'focus', 'short_title'):
                if field not in step:
                    continue
                location = route_prefix + ([i, 'steps', j, field] if route_prefix[0] == 'nav' else [[i, 'steps', j, field]])
                add(step[field], 'navigation', location,
                    '当前领域对本节的标题或导读；保持正文与领域关系')
    seen = set()
    for component in cfg.get('components', []):
        matches = tree.xpath(component['xpath'])
        if len(matches) != 1:
            raise ValueError('component_selector_must_match_once:' + component['id'])
        for node in matches[0].xpath('.//text()[not(ancestor::script) and not(ancestor::style)]'):
            parent = node.getparent()
            location = ['html_text', tree.getroottree().getpath(parent), 'tail' if node.is_tail else 'text']
            identity = tuple(location)
            if identity not in seen and str(node).strip():
                seen.add(identity)
                add(str(node), 'interface', location, component['context'], component['id'])
        for element in matches[0].iter():
            for attribute in ('title', 'aria-label', 'placeholder', 'alt'):
                if element.get(attribute):
                    location = ['html_attribute', tree.getroottree().getpath(element), attribute]
                    if tuple(location) not in seen:
                        seen.add(tuple(location))
                        add(element.get(attribute), 'interface', location, component['context'], component['id'])
    for identity in cfg.get('json_scripts', []):
        matches = tree.xpath('//script[@type="application/json" and @id=$id]', id=identity)
        if len(matches) != 1:
            raise ValueError('missing_json_script:' + identity)

        def walk(value, path):
            if isinstance(value, dict):
                for k, v in value.items():
                    walk(v, path + [k])
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    walk(v, path + [i])
            elif isinstance(value, str) and any('\u4e00' <= c <= '\u9fff' for c in value):
                add(value, 'interface', ['json', identity, path], '组件数据文案；规则数值和状态数据保持')
        walk(json.loads(matches[0].text), [])
    # Only referenced SVGs are exported. An unused asset in evidence/ is not reader text.
    references = {b['src'] for s in study['sections'] for b in s.get('blocks', []) if b.get('type') == 'image'}
    inline = set()
    for src in tree.xpath('//img/@src'):
        if src.startswith('data:image/svg+xml;base64,'):
            inline.add(hashlib.sha256(base64.b64decode(src.split(',', 1)[1])).hexdigest())
    excluded = []
    for path in sorted((report / 'evidence').rglob('*.svg')):
        relative = path.relative_to(report).as_posix()
        if relative not in references and digest(path) not in inline:
            excluded.append(relative)
            continue
        versions[relative] = digest(path)
        svg = etree.fromstring(path.read_bytes(), parser=etree.XMLParser(no_network=True, resolve_entities=False))
        for node in svg.iter():
            if isinstance(node.tag, str) and node.tag.split('}')[-1] in ('text', 'tspan') and node.text:
                add(node.text, 'svg', ['svg_text', relative, svg.getroottree().getpath(node)], '在用自绘图文字')
    anchors = deepcopy(cfg.get('anchors', []))
    for anchor in anchors:
        anchor['surfaces'] = component_surfaces.get(anchor['id'], [])
    document = dict(format='research-report-edit-v1', source_revision=versions['study.json'],
                    source=source, surfaces=surfaces,
                    presentation=dict(revision=versions['reader/index.html'], anchors=anchors))
    if cfg.get('sections'):
        document.update(sections=cfg['sections'], include_shared=cfg.get('include_shared', False),
                        brief=dict(revision=tool.report_revision(document), direction=context,
                                   sections={k: str(v) for k, v in roles.items()}))
    request = dict(profile='research', context=context, document=document)
    # Reuse the native parser and payload limit; no fixed-field splitting or new protocol.
    payload = tool.report_payload('game-research', request)
    prepared = tool.prepare_edit_request(request, 'game-research')
    if output.exists():
        raise ValueError('output_must_be_new')
    output.mkdir(parents=True)
    save(output / 'request.json', request)
    save(output / 'payload.json', payload)
    save(output / 'mapping.json', mapping)
    save(output / 'retained-metadata.json', metadata)
    save(output / 'host.json', dict(report=str(report), config=str(Path(config).resolve()),
                                  config_sha256=digest(config), versions=versions,
                                  adapter_sha256=digest(__file__),
                                  navigation_source='file' if 'reader/navigation.json' in versions else 'embedded',
                                  document=prepared[3], excluded_svg=excluded,
                                  payload_bytes=len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()),
                                  renderer=cfg.get('renderer'), network_calls=0))
    return dict(status='prepared_offline', surfaces=len(surfaces), excluded_svg=excluded)


def verify(run, report=None, config=None):
    load_executor()
    host = load(run / 'host.json')
    report = Path(report or host['report'])
    config = Path(config or host['config'])
    if host.get('navigation_source') and (report / 'reader/navigation.json').is_file() != (host['navigation_source'] == 'file'):
        raise ValueError('navigation_source_drift')
    if digest(config) != host['config_sha256']:
        raise ValueError('config_drift')
    for path, expected in host['versions'].items():
        if digest(report / path) != expected:
            raise ValueError('source_drift:' + path)
    request = load(run / 'request.json')
    if tool.prepare_edit_request(request, 'game-research')[3] != host['document']:
        raise ValueError('request_identity_drift')
    return host


def plan(run, receipt, output):
    host = verify(run)
    checked = load(receipt)
    if checked.get('status') != 'pass' or checked.get('document') != host['document']:
        raise ValueError('checked_receipt_identity_mismatch')
    # The existing renderer consumes these maps, including real paragraph split boundaries.
    result = {k: checked[k] for k in ('revised_source', 'revised_surfaces', 'revised_presentation', 'block_map', 'prose_map')}
    result.update(mapping=load(run / 'mapping.json'), retained_metadata=load(run / 'retained-metadata.json'),
                  source_versions=host['versions'], renderer=host['renderer'],
                  receipt_sha256=digest(receipt), status='pending_original_renderer_and_review')
    if Path(output).exists():
        raise ValueError('output_must_be_new')
    save(output, result)
    return dict(status=result['status'], network_calls=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    q = sub.add_parser('prepare')
    for name in ('report', 'config', 'output'):
        q.add_argument('--' + name, type=Path, required=True)
    q = sub.add_parser('verify'); q.add_argument('--run', type=Path, required=True)
    q.add_argument('--report', type=Path); q.add_argument('--config', type=Path)
    q = sub.add_parser('plan')
    for name in ('run', 'receipt', 'output'):
        q.add_argument('--' + name, type=Path, required=True)
    a = vars(p.parse_args()); action = a.pop('action')
    if action == 'verify':
        verify(**a); result = dict(status='source_identity_verified')
    else:
        result = globals()[action](**a)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
