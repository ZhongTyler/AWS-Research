"""Regression checks for source preservation and the shared reader adapter."""
import json
from pathlib import Path
import tempfile
import unittest

from build_reader import build


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'playable').mkdir()
        (self.root / 'playable/lab.html').write_text('<p>prototype</p>', encoding='utf8')
        (self.root / 'diagram.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding='utf8')
        self.source = '# 系统研究\r\n\r\n简介。\r\n\r\n## 一、规则\r\n\r\n![原图](diagram.svg)\r\n\r\n| 状态 | 动作 |\r\n|---|---|\r\n| 可用 | 购买 |\r\n\r\n## 二、操作\r\n\r\n正文。\r\n'
        (self.root / 'README.md').write_bytes(self.source.encode())
        self.config = {'schema':1, 'report_id':'regression', 'title':'系统研究',
                       'sections':[{'id':'rules','heading':'一、规则'},{'id':'actions','heading':'二、操作'}],
                       'prototype':{'path':'playable/lab.html'},
                       'routes':[{'id':'system','name':'系统策划','intro':'查看动作怎样改变状态。',
                                  'steps':[{'target':'rules','focus':'核对购买前后条件。'}]}]}

    def write_config(self):
        (self.root / 'reader.json').write_text(json.dumps(self.config, ensure_ascii=False), encoding='utf8')

    def test_full_build_preserves_source_and_uses_existing_navigation(self):
        self.write_config()
        receipt = build(self.root)
        self.assertEqual((self.root / 'README.md').read_bytes(), self.source.encode())
        output = (self.root / 'reader/index.html').read_text(encoding='utf8')
        for expected in ('id="rn-toggle"', 'id="rn-guide-rules"', '../diagram.svg', '../playable/lab.html', '<table>', 'id="prototype-dialog"'):
            self.assertIn(expected, output)
        self.assertEqual(receipt['sections'], 2)
        self.assertEqual(receipt['routes'], 1)
        self.assertTrue(receipt['navigation']['content_byte_preserved'])

    def test_zero_domains_is_supported(self):
        self.config['routes'] = []
        self.write_config()
        self.assertEqual(build(self.root)['routes'], 0)

    def test_code_heading_and_formatted_heading_preserve_real_sections(self):
        text = self.source.replace('## 二、操作', '```text\r\n## 代码中的标题\r\n```\r\n\r\n## 二、`操作`')
        (self.root / 'README.md').write_bytes(text.encode())
        self.config['sections'][1]['heading'] = '二、`操作`'
        self.config['routes'][0]['steps'].append({'target':'actions','focus':'查看操作结果。'})
        self.write_config()
        self.assertEqual(build(self.root)['sections'], 2)
        self.assertEqual((self.root / 'README.md').read_bytes(), text.encode())

    def test_missing_heading_rejected_without_overwriting_reader(self):
        self.config['sections'].pop()
        self.write_config()
        (self.root / 'reader').mkdir()
        target = self.root / 'reader/index.html'
        target.write_text('old accepted page', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'cover all'):
            build(self.root)
        self.assertEqual(target.read_text(), 'old accepted page')

    def test_toc_omission_rejected(self):
        self.config['toc_groups'] = [{'title':'目录','sections':['rules']}]
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'TOC'):
            build(self.root)

    def test_output_cannot_replace_the_prototype(self):
        self.config['output'] = 'playable/lab.html'
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'reader directory'):
            build(self.root)
        self.assertEqual((self.root / 'playable/lab.html').read_text(), '<p>prototype</p>')

    def test_unknown_domain_target_rejected(self):
        self.config['routes'][0]['steps'][0]['target'] = 'missing'
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'target'):
            build(self.root)

    def test_reserved_id_collision_rejected(self):
        self.config['sections'][1]['id'] = 'contents'
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'Duplicate rendered IDs'):
            build(self.root)

    def test_converter_heading_ids_are_remapped_with_internal_links(self):
        text = self.source.replace('正文。', '<h3 id="rules">子节</h3>\r\n\r\n[看子节](#rules)')
        (self.root / 'README.md').write_bytes(text.encode())
        self.write_config()
        build(self.root)
        output = (self.root / 'reader/index.html').read_text(encoding='utf8')
        self.assertIn('id="md-rules"', output)
        self.assertIn('href="#md-rules"', output)
        self.assertEqual(output.count('id="rules"'), 1)

    def test_resource_url_preserves_encoded_filename_query_and_fragment(self):
        (self.root / 'a#b.svg').write_text('<svg/>', encoding='utf8')
        text = self.source.replace('diagram.svg', 'a%23b.svg?view=1#shape')
        (self.root / 'README.md').write_bytes(text.encode())
        self.write_config()
        build(self.root)
        output = (self.root / 'reader/index.html').read_text(encoding='utf8')
        self.assertIn('../a%23b.svg?view=1#shape', output)
        self.assertEqual((self.root / 'README.md').read_bytes(), text.encode())

    def test_prototype_filename_keeps_hash_as_path(self):
        (self.root / 'playable/lab#variant.html').write_text('<p>variant</p>', encoding='utf8')
        self.config['prototype']['path'] = 'playable/lab#variant.html'
        self.write_config()
        build(self.root)
        output = (self.root / 'reader/index.html').read_text(encoding='utf8')
        self.assertIn('../playable/lab%23variant.html', output)


if __name__ == '__main__':
    unittest.main()
