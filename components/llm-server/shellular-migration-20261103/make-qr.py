from pathlib import Path
import subprocess,json,zlib,struct,os
h=Path.home();script=r'''
const fs=require('fs');
const root=process.env.HOME;
const cfg=JSON.parse(fs.readFileSync(root+'/.shellular/config.json','utf8'));
const unit=fs.readFileSync(root+'/.config/systemd/user/shellular.service','utf8');
const match=unit.match(/Environment=SHELLULAR_MIGRATED_MACHINE_ID=([^\s]+)/);
const machine=match?match[1]:cfg.machineId;
const key=fs.readFileSync(root+'/.shellular/shellular-'+machine+'.e2ee');
if(key.length!==32||!cfg.hostId)throw new Error('Invalid pairing state');
const QR=require(root+'/OpenCode/shellular/packages/cli/node_modules/qrcode-terminal/vendor/QRCode');
const level=require(root+'/OpenCode/shellular/packages/cli/node_modules/qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel');
const qr=new QR(-1,level.M);qr.addData(cfg.hostId+':'+key.toString('base64'));qr.make();
console.log(JSON.stringify(qr.modules));
'''
m=json.loads(subprocess.check_output(['/home/somdutta/.nvm/versions/node/v24.22.1/bin/node','-e',script],text=True));scale=10;border=4;n=len(m);size=(n+border*2)*scale
raw=bytearray()
for y in range(size):
 raw.append(0)
 for x in range(size):
  row=y//scale-border;col=x//scale-border
  raw.append(0 if 0<=row<n and 0<=col<n and m[row][col] else 255)
def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(raw)))+chunk(b'IEND',b'')
p=h/'llm-server/shellular-migration-20261103/shellular-evo-qr.png';p.write_bytes(data);p.chmod(0o600)
print(json.dumps({'file':str(p),'size':size,'source':'current service pairing identity'}))
