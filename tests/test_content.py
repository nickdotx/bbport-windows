from paths import ROOT
from pathlib import Path
import json
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import content_profile

EXE=ROOT/'out/content-test'

class ProfileTests(unittest.TestCase):
    def test_sfo_parameters_and_explicit_trial_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'sce_sys').mkdir();(p/'sce_sys/param.sfo').write_bytes(b'fixture')
            with patch.object(content_profile,'sfo',return_value={'USER_DEFINED_PARAM_1':13,'USER_DEFINED_PARAM_4':0xffffffff}):
                content_profile.prepare(p,p,'trial')
            self.assertEqual(struct.unpack('<8s5I',(p/'content.bin').read_bytes()),(b'BBCONT01',1,13,0,0,0xffffffff))
            self.assertEqual(json.loads((p/'content-profile.json').read_text())['addons'],[])

    def test_invalid_sfo_parameter_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'sce_sys').mkdir();(p/'sce_sys/param.sfo').write_bytes(b'fixture')
            with patch.object(content_profile,'sfo',return_value={'USER_DEFINED_PARAM_1':'13'}):
                with self.assertRaisesRegex(ValueError,'invalid user-defined'):
                    content_profile.prepare(p,p)

    def test_addon_licence_folders_are_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'sce_sys').mkdir();(p/'sce_sys/param.sfo').write_bytes(b'fixture')
            (p/'dvdroot_ps4').mkdir();(p/'sce_module').mkdir()
            for name in ('SPEXPANSIONDLC03','SPDLCMESSENGER00'):
                (p/name/'sce_sys').mkdir(parents=True);(p/name/'sce_sys/license.dat').write_bytes(b'x')
            (p/'SPDLCMESSENGER01'/'sce_sys').mkdir(parents=True)  # no licence file: not an add-on
            (p/'addcont'/'SPDLCMESSENGER02').mkdir(parents=True)  # console-style addcont folder
            with patch.object(content_profile,'sfo',return_value={'USER_DEFINED_PARAM_1':2}):
                content_profile.prepare(p,p)
            expected=['SPDLCMESSENGER00','SPDLCMESSENGER02','SPEXPANSIONDLC03']
            self.assertEqual(content_profile.addon_labels(p),expected)
            self.assertEqual(json.loads((p/'content-profile.json').read_text())['addons'],expected)
            self.assertEqual(struct.unpack('<8s5I',(p/'content.bin').read_bytes()),(b'BBCONT01',3,2,0,0,0))

@unittest.skipUnless(EXE.exists(),'run bash build.sh --test first')
class ContentTests(unittest.TestCase):
    def run_case(self,*args):
        return subprocess.run([str(EXE.resolve()),*args],capture_output=True,text=True,timeout=5)

    def test_lifecycle_and_output_boundaries(self):
        r=self.run_case();self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_missing_profile_does_not_report_loaded(self):
        r=self.run_case('--missing');self.assertEqual(r.returncode,21)
        self.assertIn('needs --content-profile',r.stderr)

    def test_other_modules_are_counted_independently(self):
        r=self.run_case('--unknown');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
