"""Read a Markdown primary report and add the existing research reader navigation.

Requires PowerShell 7 ConvertFrom-Markdown and the existing lxml environment.
Case-specific headings and reviewed guidance live in reader.json.
"""
import argparse
import copy
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlsplit

from lxml import etree, html as tree

HERE = Path(__file__).resolve().parent
NAVIGATION = HERE.parent / 'deep-game-analysis/reader-navigation/build.py'
ASSETS = HERE / 'reader-assets'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def local(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('Expected a relative case path')
    result = (root / value).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Case path escapes case root: ' + value)
    return result


def load_navigation():
    spec = importlib.util.spec_from_file_location('system_reader_navigation', NAVIGATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(config, markdown):
    if config.get('schema') != 1:
        raise ValueError('reader.json requires schema=1')
    if not config.get('report_id') or not config.get('title'):
        raise ValueError('Missing report identity/title')
    sections = config['sections']
    headings = []
    fence = None
    for line in markdown.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            current = marker.group(1)
            if fence is None:
                fence = current
            elif current[0] == fence[0] and len(current) >= len(fence):
                fence = None
            continue
        if fence is None and line.startswith('## '):
            headings.append(line[3:].strip())
    if [section['heading'] for section in sections] != headings:
        raise ValueError('Sections must cover all Markdown H2 headings in order')
    ids = [section['id'] for section in sections]
    if not ids or len(ids) != len(set(ids)) or len(headings) != len(set(headings)):
        raise ValueError('Empty or duplicate section identity/heading')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', key) for key in ids):
        raise ValueError('Section IDs must be portable identifiers')
    groups = config.get('toc_groups') or [{'title':'目录', 'sections':ids}]
    if [key for group in groups for key in group['sections']] != ids:
        raise ValueError('TOC must cover each section once in report order')
    routes = config.get('routes', [])
    route_ids = [route['id'] for route in routes]
    if len(route_ids) != len(set(route_ids)):
        raise ValueError('Duplicate domain route')
    for route in routes:
        if not route.get('name', '').strip() or not route.get('intro', '').strip() or not route.get('steps'):
            raise ValueError('Domain needs name, substantive intro and steps')
        targets = [step['target'] for step in route['steps']]
        if len(targets) != len(set(targets)):
            raise ValueError('Repeated section within a route')
        for step in route['steps']:
            if step['target'] not in ids or not step.get('focus', '').strip():
                raise ValueError('Missing route target or reviewed section guidance')
    return groups


def markdown_html(source, powershell):
    command = (
        '[Console]::InputEncoding=[Text.UTF8Encoding]::new(); '
        '[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); '
        '$ErrorActionPreference="Stop"; '
        '(ConvertFrom-Markdown -InputObject ([Console]::In.ReadToEnd())).Html'
    )
    result = subprocess.run(
        [powershell, '-NoProfile', '-NonInteractive', '-Command', command],
        input=source, encoding='utf-8', capture_output=True, timeout=45, check=True,
    )
    return result.stdout


def build(case, powershell=None):
    case = case.resolve()
    config_path = case / 'reader.json'
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes.decode('utf-8-sig'))
    source = local(case, config.get('source', 'README.md'))
    if source.suffix.lower() != '.md':
        raise ValueError('The report primary must be a Markdown file')
    output = local(case, config.get('output', 'reader/index.html'))
    if not output.is_relative_to(case / 'reader') or output.suffix != '.html':
        raise ValueError('HTML output must stay inside the case reader directory')
    prototype = local(case, config['prototype']['path'])
    if not prototype.is_file():
        raise ValueError('Prototype entry does not exist')
    if output == prototype:
        raise ValueError('Output would overwrite the prototype')
    raw = source.read_bytes()
    markdown = raw.decode('utf-8-sig').replace('\r\n', '\n')
    groups = validate(config, markdown)
    powershell = powershell or shutil.which('pwsh')
    if not powershell:
        raise ValueError('PowerShell 7 is required; provide --powershell')
    fragment = tree.fragment_fromstring(markdown_html(markdown, powershell), create_parent='div')
    # Preserve original resource/link targets when moving the projection to reader/.
    for element in fragment.xpath('//*[@href or @src]'):
        for attribute in ('href', 'src'):
            value = element.get(attribute)
            if not value or value.startswith('#'):
                continue
            parts = urlsplit(value)
            if parts.scheme or parts.netloc:
                continue
            if not parts.path:
                continue
            target = (source.parent / unquote(parts.path)).resolve()
            if not target.is_file():
                raise ValueError('Missing linked report resource: ' + value)
            relative = quote(Path(os.path.relpath(target, output.parent)).as_posix(), safe='/')
            if parts.query:
                relative += '?' + parts.query
            if parts.fragment:
                relative += '#' + parts.fragment
            element.set(attribute, relative)
    cover = tree.Element('header', id='book-cover')
    main = tree.Element('main')
    current = cover
    section_index = 0
    title_by_id = {}
    heading_targets = {}
    for element in list(fragment):
        if element.tag == 'h2':
            spec = config['sections'][section_index]
            current = etree.SubElement(main, 'section', id=spec['id'], attrib={'data-scene':spec['id']})
            old_id = element.get('id')
            if old_id:
                heading_targets[old_id] = spec['id']
                element.attrib.pop('id')
            title_by_id[spec['id']] = element.text_content().strip()
            section_index += 1
        current.append(element)
    if section_index != len(config['sections']):
        raise ValueError('Rendered Markdown section coverage differs')
    for parent in (cover, main):
        for heading in parent.xpath('.//*[self::h1 or self::h3 or self::h4 or self::h5 or self::h6][@id]'):
            original_id = heading.get('id')
            heading_targets[original_id] = 'md-' + original_id
            heading.set('id', 'md-' + original_id)
    for parent in (cover, main):
        for anchor in parent.xpath('.//a[starts-with(@href,"#")]'):
            target = unquote(anchor.get('href')[1:])
            if target in heading_targets:
                anchor.set('href', '#' + heading_targets[target])
    contents = tree.Element('nav', id='contents', attrib={'aria-label':'目录'})
    for group in groups:
        container = etree.SubElement(contents, 'div')
        etree.SubElement(container, 'h3').text = group['title']
        listing = etree.SubElement(container, 'ol')
        for key in group['sections']:
            item = etree.SubElement(listing, 'li')
            etree.SubElement(item, 'a', href='#' + key).text = title_by_id[key]
    cover.append(contents)
    serialize = lambda element: tree.tostring(element, encoding='unicode', method='html')
    esc = html.escape
    prototype_url = quote(Path(os.path.relpath(prototype, output.parent)).as_posix(), safe='/')
    label = config['prototype'].get('label', '打开可运行原型')
    overlay = (
        '<button id="prototype-toggle" aria-controls="prototype-dialog" aria-expanded="false">' + esc(label) + '</button>'
        '<dialog id="prototype-dialog" aria-labelledby="prototype-title">'
        '<div class="prototype-toolbar"><strong id="prototype-title">可运行原型</strong>'
        '<button id="prototype-close" aria-label="关闭原型并返回报告">关闭原型</button></div>'
        '<p id="prototype-status" role="status"></p>'
        '<iframe id="prototype-frame" title="可运行原型" data-src="' + esc(prototype_url, quote=True) + '"></iframe></dialog>'
    )
    page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + esc(config['title']) + '</title><style>' + (ASSETS / 'reader.css').read_text(encoding='utf-8') + '</style></head><body>'
            + serialize(cover) + serialize(main) + overlay
            + '<script>' + (ASSETS / 'prototype.js').read_text(encoding='utf-8') + '</script></body></html>')
    # Adapt source identity to the existing navigation contract in a temporary build.
    routes = copy.deepcopy(config.get('routes', []))
    matches = list(re.finditer(r'^#{1,2} .+$', markdown, re.M))
    hashes = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        heading = re.sub(r'^#+ ', '', match.group()).strip()
        hashes[heading] = sha(markdown[match.start():end].strip().encode())
    navigation = load_navigation()
    heading_by_id = {section['id']:section['heading'] for section in config['sections']}
    with tempfile.TemporaryDirectory(prefix='system-reader-') as directory:
        stage = Path(directory)
        (stage / 'reader').mkdir()
        (stage / 'README.md').write_text(markdown, encoding='utf-8', newline='\n')
        (stage / 'reader/index.html').write_text(page, encoding='utf-8', newline='\n')
        manifest = {'documents':{'README.md':sha(markdown.encode())}, 'sources':[], 'domains':[]}
        for route in routes:
            manifest['domains'].append({'name':route['name'], 'chapter':'README.md', 'reader_visible':True})
            for step in route['steps']:
                heading = heading_by_id[step['target']]
                step['title'] = title_by_id[step['target']]
                step['source'] = {'file':'README.md', 'heading':heading, 'role':'primary', 'detail_target':step['target'],
                                  'document_sha256':sha(markdown.encode()), 'section_sha256':hashes[heading]}
        nav_config = {'report_id':config['report_id'], 'title':config['title'], 'base_html_sha256':sha(page.encode()), 'routes':routes}
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        (stage / 'reader/navigation.json').write_text(json.dumps(nav_config, ensure_ascii=False), encoding='utf-8')
        nav_receipt = navigation.build(stage)
        rendered = (stage / 'reader/index.html').read_bytes()
    rendered_ids = tree.fromstring(rendered).xpath('//*[@id]/@id')
    if len(rendered_ids) != len(set(rendered_ids)):
        raise ValueError('Duplicate rendered IDs would break report navigation')
    if source.read_bytes() != raw or config_path.read_bytes() != config_bytes:
        raise ValueError('Authored input changed during build; retry from current source')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.html.tmp')
    temporary.write_bytes(rendered)
    temporary.replace(output)
    receipt = {'schema':1, 'source':source.relative_to(case).as_posix(), 'source_sha256':sha(raw),
               'config_sha256':sha(config_bytes), 'output':output.relative_to(case).as_posix(), 'output_sha256':sha(rendered),
               'prototype':config['prototype']['path'], 'prototype_sha256':sha(prototype.read_bytes()),
               'sections':len(config['sections']), 'routes':len(routes), 'navigation':nav_receipt,
               'boundary':'Build and source binding only; content, polishing, browser behavior and acceptance require their own evidence.'}
    receipt['renderer_inputs'] = {
        str(path.relative_to(HERE.parent)):sha(path.read_bytes()) for path in
        (Path(__file__).resolve(), NAVIGATION, NAVIGATION.with_name('navigation.css'),
         NAVIGATION.with_name('navigation.js'), ASSETS / 'reader.css', ASSETS / 'prototype.js')
    }
    output.with_name('build-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    parser.add_argument('--powershell')
    args = parser.parse_args()
    print(json.dumps(build(args.case, args.powershell), ensure_ascii=False))
