"""Prepare explicit offline AppContent metadata; SKU is a probe setting, not a license check.

Add-ons: a dump carries each licensed add-on as a folder beside dvdroot_ps4 named by its
entitlement label (Bloodborne: SPDLCMESSENGER00, SPDLCMESSENGER01, SPEXPANSIONDLC03), holding
only sce_sys/license.dat. The game never mounts add-on data: it asks
sceAppContentGetAddcontInfoList for the labels and keys its DLC table by their last two digits.
The labels found are listed in content-profile.json; content.bin keeps the BBCONT01 layout
until the runtime answers the list."""
import argparse
import json
import re
import struct
from pathlib import Path
from prepare import sfo

LABEL = re.compile(r'^[A-Z0-9]{1,16}$')


def addon_labels(game):
    """Entitlement labels of the add-ons in the dump, sorted: a folder named like a label
    beside dvdroot_ps4 with a licence, or any folder under addcont/."""
    labels = set()
    for d in game.iterdir():
        if d.is_dir() and LABEL.match(d.name) and (d / 'sce_sys' / 'license.dat').is_file():
            labels.add(d.name)
    addcont = game / 'addcont'
    if addcont.is_dir():
        labels.update(d.name for d in addcont.iterdir() if d.is_dir() and LABEL.match(d.name))
    return sorted(labels)


def prepare(game, out, sku='full'):
    values=sfo((game/'sce_sys/param.sfo').read_bytes())
    params=[values.get(f'USER_DEFINED_PARAM_{i}',0) for i in range(1,5)]
    if any(type(v) is not int or not 0<=v<=0xffffffff for v in params):
        raise ValueError('invalid user-defined parameter')
    addons=addon_labels(game)
    profile=dict(title_id=values.get('TITLE_ID'),sku=sku,sku_source='explicit probe setting',
                 user_params=params, mounted_addons=[], addons=addons, boot_attr=0)
    out.mkdir(parents=True,exist_ok=True)
    (out/'content.bin').write_bytes(struct.pack('<8s5I',b'BBCONT01',{'full':3,'trial':1}[sku],*params))
    (out/'content-profile.json').write_text(json.dumps(profile,indent=2)+'\n')
    print(f'AppContent profile: SKU={sku} (probe setting), user params={params}, mounted add-ons=0; '
          f'add-on licences in the dump: {", ".join(addons) if addons else "none"} (not answered by the runtime yet)')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('game',type=Path)
    p.add_argument('--out',type=Path,default=Path(__file__).resolve().parent.parent/'out')
    p.add_argument('--sku',choices=['full','trial'],default='full')
    a=p.parse_args();prepare(a.game,a.out,a.sku)
