"""Double-click launch: browser workbench on loopback only. Python 3.11+."""
import sys
if sys.version_info < (3,11):
    raise SystemExit('需要 Python 3.11 或更高版本。')
from deepaha_importer.workbench import main
if __name__=='__main__':
    main()
