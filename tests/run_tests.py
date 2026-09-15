from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work'
WORK.mkdir(exist_ok=True)
RUN=Path(tempfile.mkdtemp(prefix='test-run-',dir=WORK))
class PreservedTemporaryDirectory:
    def __init__(self,*args,**kwargs):
        self.name=tempfile.mkdtemp(prefix='fixture-',dir=RUN)
    def __enter__(self): return self.name
    def __exit__(self,*args): return False
tempfile.TemporaryDirectory=PreservedTemporaryDirectory
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'scripts'))
suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
with (RUN/'results.txt').open('x',encoding='utf-8') as output:
    result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
print((RUN/'results.txt').read_text(encoding='utf-8'))
print('Preserved fixtures:',RUN)
sys.exit(not result.wasSuccessful())
