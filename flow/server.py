"""The local server moved to admin/server.py, which serves the storefront at
http://localhost:4310/ and the admin at http://localhost:4310/admin/, on
127.0.0.1 only. This file stays so the existing preview command
(python3 flow/server.py 4310) keeps working: it only starts that server.
Nothing of the admin lives here: flow/ is the directory the deploys publish
from (this file itself is not among the files they copy).
"""
import os
import sys

target = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "admin", "server.py")
os.execv(sys.executable, [sys.executable, os.path.normpath(target)] + sys.argv[1:])
