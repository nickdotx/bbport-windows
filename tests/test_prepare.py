from paths import ROOT
import hashlib
import struct
import unittest
import tempfile
from pathlib import Path
from unittest import mock
import prepare
from prepare import parse_self, inspect_libc, nid, self_digest


def fixture():
    data = bytearray(0x210)
    data[:4] = b'O\x15=\x1d'
    struct.pack_into('<H', data, 24, 1)
    struct.pack_into('<QQQQ', data, 32, 0x800, 0x200, 16, 16)
    struct.pack_into('<16sHHIQQQIHHHHHH', data, 64,
                     b'\x7fELF\x02\x01\x01\x09', 0xfe10, 62, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', data, 128, 1, 5, 0x1000, 0, 0, 16, 32, 0x1000)
    data[0x200:] = bytes(range(16))
    return data


def fixture_with_comment():
    """A SELF whose PT_SCE_COMMENT is not a blocked segment: its bytes follow the SELF's declared
    file size, and the extended header carries the SHA-256 of the original ELF."""
    original = bytearray(0x1018)
    struct.pack_into('<16sHHIQQQIHHHHHH', original, 0,
                     b'\x7fELF\x02\x01\x01\x09', 0xfe10, 62, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', original, 64, 1, 5, 0x1000, 0, 0, 16, 32, 0x1000)
    struct.pack_into('<IIQQQQQQ', original, 120, 0x6fffff01, 0, 0x1010, 0, 0, 8, 0, 16)
    original[0x1000:0x1010] = bytes(range(16))
    original[0x1010:0x1018] = b'COMMENT!'
    data = bytearray(0x210)
    data[:4] = b'O\x15=\x1d'
    struct.pack_into('<Q', data, 16, 0x210)  # declared file size: the blocked segments end here
    struct.pack_into('<H', data, 24, 1)
    struct.pack_into('<QQQQ', data, 32, 0x800, 0x200, 16, 16)
    data[64:64 + 176] = original[:176]  # ELF header and program headers
    data[240 + 32:240 + 64] = hashlib.sha256(original).digest()  # extended header: digest
    data[0x200:0x210] = original[0x1000:0x1010]
    data += original[0x1010:0x1018]  # the comment segment, after the declared file size
    return bytes(data), bytes(original)


class SelfTests(unittest.TestCase):
    def test_unblocked_comment_segment_restored_from_the_self_tail(self):
        data, original = fixture_with_comment()
        elf, header, ph, segments, missing = parse_self(data)
        self.assertEqual(bytes(elf), original)
        self.assertEqual(missing, [])
        self.assertEqual(self_digest(data), hashlib.sha256(original).hexdigest())

    def test_comment_segment_without_tail_stays_missing(self):
        data, original = fixture_with_comment()
        elf, header, ph, segments, missing = parse_self(data[:0x210])  # a dump without the tail
        self.assertEqual(missing, [1])
        self.assertEqual(len(elf), len(original))
        self.assertEqual(elf[0x1010:0x1018], bytes(8))

    def test_eboot_elf_is_written_before_the_dump_is_required_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            game, out = Path(tmp) / 'game', Path(tmp) / 'out'
            game.mkdir()
            (game / 'eboot.bin').write_bytes(fixture())
            with mock.patch.object(prepare.game_check, 'problem', return_value=None):
                with self.assertRaisesRegex(ValueError, 'sce_module/libc.prx'):
                    prepare.prepare(game, out)
            self.assertEqual((out / 'eboot.elf').read_bytes(), bytes(parse_self(fixture())[0]))

    def test_incomplete_dump_names_every_empty_or_missing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            for name in prepare.BUNDLED_MODULES:
                (game / 'sce_module' / name).parent.mkdir(exist_ok=True)
                (game / 'sce_module' / name).write_bytes(b'x')
            for folder in prepare.DVDROOT_FOLDERS:
                (game / 'dvdroot_ps4' / folder).mkdir(parents=True)
                (game / 'dvdroot_ps4' / folder / 'a.bin').write_bytes(b'x')
            prepare.require_dump(game)  # complete: no complaint
            (game / 'dvdroot_ps4' / 'shader' / 'a.bin').unlink()  # left empty by an interrupted copy
            import shutil
            shutil.rmtree(game / 'dvdroot_ps4' / 'sound')
            with self.assertRaisesRegex(ValueError, r'dvdroot_ps4/shader \(empty\).*dvdroot_ps4/sound \(missing\)'):
                prepare.require_dump(game)
            (game / 'sce_module' / 'libc.prx').unlink()
            with self.assertRaisesRegex(ValueError, r'sce_module/libc.prx \(missing\).*dvdroot_ps4/shader'):
                prepare.require_dump(game)

    def test_libc_ret_contract_is_verified_from_symbol_and_code(self):
        def libc(instruction):
            data=bytearray(0x320)
            data[:4]=b'O\x15=\x1d'
            struct.pack_into('<H',data,24,2)
            struct.pack_into('<QQQQ',data,32,0x800,0x200,16,16)
            struct.pack_into('<QQQQ',data,64,0x100800,0x220,256,256)
            struct.pack_into('<16sHHIQQQIHHHHHH',data,96,b'\x7fELF\x02\x01\x01\x09',0xfe18,62,1,0,64,0,0,64,56,3,0,0,0)
            struct.pack_into('<IIQQQQQQ',data,160,1,5,0x1000,0,0,16,16,0x1000)
            struct.pack_into('<IIQQQQQQ',data,216,0x61000000,4,0x2000,0,0,256,0,16)
            struct.pack_into('<IIQQQQQQ',data,272,2,4,0x20b0,0,0,80,80,8)
            data[0x200]=instruction
            name=b'bzQExy189ZI#C#A\0'
            data[0x220:0x220+len(name)]=name
            struct.pack_into('<IBBHQQ',data,0x260,0,0x12,0,1,0,1)
            for i,(tag,value) in enumerate([(0x61000035,0),(0x61000037,32),(0x61000039,64),(0x6100003f,24),(0,0)]):
                struct.pack_into('<QQ',data,0x2d0+16*i,tag,value)
            return data
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'libc.prx'
            path.write_bytes(libc(0xc3))
            proof=inspect_libc(path)
            self.assertTrue(proof['init_env_is_ret'])
            self.assertEqual(proof['bytes'],'c3')
            path.write_bytes(libc(0x90))
            self.assertFalse(inspect_libc(path)['init_env_is_ret'])
        self.assertEqual(nid('_init_env'),'bzQExy189ZI')

    def test_file_offset_is_not_virtual_address(self):
        elf, header, ph, segments, missing = parse_self(fixture())
        self.assertEqual(elf[0x1000:0x1010], bytes(range(16)))
        self.assertEqual(ph[0]['vaddr'], 0)
        self.assertEqual(missing, [])

    def test_truncated_payload_rejected(self):
        with self.assertRaisesRegex(ValueError, 'out of bounds'):
            parse_self(fixture()[:-1])

    def test_encrypted_or_compressed_payload_rejected(self):
        for flag in (2, 8):
            data = fixture()
            struct.pack_into('<Q', data, 32, 0x800 | flag)
            with self.assertRaisesRegex(ValueError, 'encrypted/compressed'):
                parse_self(data)

    def test_missing_required_segment_rejected(self):
        data = fixture()
        struct.pack_into('<Q', data, 32, 0)
        with self.assertRaisesRegex(ValueError, 'required segment'):
            parse_self(data)

    def test_bad_program_header_index_rejected(self):
        data = fixture()
        struct.pack_into('<Q', data, 32, 0x100800)
        with self.assertRaisesRegex(ValueError, 'segment index'):
            parse_self(data)


if __name__ == '__main__':
    unittest.main()
