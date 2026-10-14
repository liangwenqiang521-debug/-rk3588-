# -*- coding: utf-8 -*-
"""把 tools/_stage39/ 里的 39 类样本批量上传到板端 /root/rknn/samples/。

步骤：备份原 6 类样本 → 清空 samples → 逐张 sftp 上传 → 报数。
用法：  C:/Users/21191/.workbuddy/binaries/python/envs/default/Scripts/python.exe tools/_upload_samples39.py
（需 paramiko，故用托管 default 环境）
"""
import os
import sys
import glob

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import board_ssh  # noqa: E402

STAGE = os.path.join(_ROOT, 'tools', '_stage39')
REMOTE_DIR = '/root/rknn/samples'
BACKUP_DIR = '/root/rknn/samples_neu6_bak'


def main():
    files = sorted(glob.glob(os.path.join(STAGE, '*.jpg')))
    if not files:
        raise SystemExit('staging 为空，请先跑 tools/_pick_samples39.py')

    c = board_ssh.connect()
    try:
        out, err, _ = board_ssh.run(c, (
            'mkdir -p %s; cp -f %s/* %s/ 2>/dev/null; '
            'rm -f %s/*.jpg %s/*.png %s/*.npy %s/*.bmp; '
            'echo BACKUP=$(ls %s | wc -l) LEFT=$(ls %s | wc -l)'
            % (BACKUP_DIR, REMOTE_DIR, BACKUP_DIR,
               REMOTE_DIR, REMOTE_DIR, REMOTE_DIR, REMOTE_DIR,
               BACKUP_DIR, REMOTE_DIR)
        ))
        print(out.strip() or err.strip())

        sftp = c.open_sftp()
        ok = 0
        for f in files:
            name = os.path.basename(f)
            try:
                sftp.put(f, REMOTE_DIR + '/' + name)
                ok += 1
            except Exception as e:
                print('  FAIL %s: %s' % (name, e))
        sftp.close()
        print('上传成功 %d/%d' % (ok, len(files)))

        out, err, _ = board_ssh.run(c, 'ls %s | head -45; echo ---; ls %s | wc -l'
                                    % (REMOTE_DIR, REMOTE_DIR))
        print(out.rstrip())
    finally:
        c.close()


if __name__ == '__main__':
    main()
