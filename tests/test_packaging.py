"""Tiny sparse fixtures: no multi-gigabyte payload and no device I/O."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import uuid

spec=importlib.util.spec_from_file_location('packager',Path(__file__).resolve().parents[1]/'tools/package_image.py')
packager=importlib.util.module_from_spec(spec);spec.loader.exec_module(packager)

class PackagingTests(unittest.TestCase):
    def fixture(self,directory,identity='93afcbbe-875f-49b0-83da-ee8193f20ca5'):
        path=Path(directory)/'tiny.sparse'
        raw=bytearray(4096);raw[1080:1082]=b'\x53\xef';raw[1128:1144]=uuid.UUID(identity).bytes
        data=struct.pack('<I4H4I',0xed26ff3a,1,0,28,12,4096,1048576,2,0)
        data+=struct.pack('<HHII',0xcac1,0,1,4108)+raw
        data+=struct.pack('<HHII',0xcac3,0,1048575,12)
        path.write_bytes(data);return path

    def test_valid_sparse_and_uuid(self):
        with tempfile.TemporaryDirectory() as d:packager.check_sparse(self.fixture(d))

    def test_wrong_uuid_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'UUID'):packager.check_sparse(self.fixture(d,'00000000-0000-0000-0000-000000000000'))

    def test_truncated_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fixture(d);p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaises(ValueError):packager.check_sparse(p)

    def test_trailing_payload_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fixture(d);p.write_bytes(p.read_bytes()+b'extra')
            with self.assertRaises(ValueError):packager.check_sparse(p)

    def test_unknown_chunk_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fixture(d);data=bytearray(p.read_bytes());struct.pack_into('<H',data,28,0xffff);p.write_bytes(data)
            with self.assertRaises(ValueError):packager.check_sparse(p)
