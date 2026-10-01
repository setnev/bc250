"""The supplemental probe must verify destination bytes and preserve boundaries."""
import hashlib, os, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
from file_restore_probe import restored_file

class RestoreProbeTests(unittest.TestCase):
    def test_actual_hash_mode_and_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'restore-file.txt';data=b'SYNTHETIC_RESTORED_CONTENT\n'
            path.write_bytes(data);path.chmod(0o644);before=path.stat()
            result=restored_file(root)
            self.assertEqual((result['sha256'],result['mode'],result['bytes']),(hashlib.sha256(data).hexdigest(),'0644',len(data)))
            self.assertEqual((path.read_bytes(),path.stat().st_mtime_ns),(data,before.st_mtime_ns))

    def test_backup_presence_does_not_hide_wrong_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'backups').mkdir();(root/'backups/restore-file.txt').write_bytes(b'GOOD')
            self.assertFalse(restored_file(root)['exists'])
            (root/'restore-file.txt').write_bytes(b'WRONG')
            self.assertNotEqual(restored_file(root)['sha256'],hashlib.sha256(b'GOOD').hexdigest())

    def test_symlink_and_nonregular_target_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);outside=root/'protected';outside.write_bytes(b'PRIVATE_TEST_VALUE')
            path=root/'restore-file.txt';path.symlink_to(outside)
            self.assertIn('error',restored_file(root));path.unlink();os.mkfifo(path)
            self.assertIn('error',restored_file(root));self.assertEqual(outside.read_bytes(),b'PRIVATE_TEST_VALUE')

    def test_oversized_file_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'restore-file.txt').write_bytes(b'x'*(1024*1024+1))
            self.assertIn('error',restored_file(root))

    def test_replaced_path_cannot_be_reported_as_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'restore-file.txt';path.write_bytes(b'OLD')
            read=os.read;replaced=False
            def replace_after_read(fd,size):
                nonlocal replaced
                data=read(fd,size)
                if not replaced:
                    replacement=root/'replacement';replacement.write_bytes(b'NEW')
                    replacement.replace(path);replaced=True
                return data
            with patch('file_restore_probe.os.read',side_effect=replace_after_read):
                self.assertIn('error',restored_file(root))

if __name__=='__main__':unittest.main()
