"""Publish: review, commit and go live, against throwaway repositories.

    ADMIN_PUBLISH_PORT=4782 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_publish.py'

The server tests run on a clone of this repository, on a branch named main,
whose origin is a bare repository in the same temporary folder, seeded from
the clone. The admin runs on it with --no-push, as always, so the push
endpoint must refuse. The push itself is tested by calling gitops.push and
publishing.go_live directly, against a second tiny repository and its own
bare remote. Nothing is pushed anywhere else.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

from box import ADMIN, REPO, Box

sys.path.insert(0, str(ADMIN))
from bgsadmin import gitops, publishing  # noqa: E402
from bgsadmin.config import Config  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402

PORT = int(os.environ.get("ADMIN_PUBLISH_PORT", "4782"))


def git(cwd, *args, check=True):
    p = subprocess.run(["git", "-C", str(cwd)] + list(args), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), p.stderr))
    return p.stdout.strip()


def identity(repo):
    git(repo, "config", "user.name", "Publish Test")
    git(repo, "config", "user.email", "publish-test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")


class Fixture(Box):
    """Box's helpers on a clone whose origin is a local bare repository."""

    def __init__(self, port):
        # Box's clone, exit nets, store and server; only the remote differs
        self._clone(port, prefix="bgsadmin-publish-")
        self.remote = pathlib.Path(self.tmp) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        git(self.repo, "checkout", "-q", "-B", "main")
        identity(self.repo)
        git(self.repo, "remote", "set-url", "origin", str(self.remote))
        git(self.repo, "push", "-q", "origin", "main")        # seeds the throwaway bare repository
        git(self.repo, "fetch", "-q", "--prune", "origin")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self._start()


class PublishServerTests(unittest.TestCase):
    """Through the server, which runs with --no-push."""

    @classmethod
    def setUpClass(cls):
        cls.b = Fixture(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def setUp(self):
        # every test starts from a clean tree at whatever HEAD is now
        git(self.b.repo, "checkout", "-q", "--", ".")
        git(self.b.repo, "clean", "-q", "-f", "-d")

    def price(self, pid, delta):
        st, d = self.b.api("GET", "products/" + pid)
        self.assertEqual(st, 200, d)
        new = d["data"]["price"] + delta
        st, res = self.b.api("PUT", "products/" + pid, {"data": dict(d["data"], price=new)}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        return new

    def changes(self):
        st, ch = self.b.api("GET", "publish/changes")
        self.assertEqual(st, 200, ch)
        return ch

    def commit(self, message, digest):
        return self.b.api("POST", "publish/commit", {"message": message, "paths_digest": digest})

    def head(self):
        return git(self.b.repo, "rev-parse", "HEAD")

    def settings_change(self, **store):
        st, d = self.b.api("GET", "documents/settings")
        self.assertEqual(st, 200, d)
        data = dict(d["data"], store=dict(d["data"]["store"], **store))
        st, res = self.b.api("PUT", "documents/settings", {"data": data}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        return res

    def test_a_delivery_rule_reaches_the_checkout_pages(self):
        """Checkout and the order-confirmed page are locked to the developer,
        but they keep no delivery numbers of their own any more: build.py
        prints their rows from the rules. So a raised threshold reaches them
        with everything else, nothing warns that a locked page has fallen
        behind (lint.LOCKED_PAGES is empty), and the change goes live."""
        b = self.b
        # A settings change that touches no delivery rule commits fine.
        self.settings_change(name="BGS Corner Test")
        ch = self.changes()
        self.assertNotIn("locked_pages", [x["id"] for x in ch["blocking"]])
        self.assertTrue(ch["can_commit"], ch["blocking"])
        git(b.repo, "checkout", "-q", "--", ".")
        git(b.repo, "clean", "-q", "-f", "-d")
        # Raising free delivery updates the strip, product page and bag, and
        # the two locked pages with them.
        res = self.settings_change(free_delivery_over=200)
        self.assertEqual([w for w in res["warnings"] if w["code"] == "locked_page"], [])
        for page in ("checkout.html", "confirmed.html"):
            text = (b.repo / "flow" / page).read_text(encoding="utf-8")
            self.assertIn("AED 200", text, page)
            self.assertNotIn("AED 150", text, page)
        ch = self.changes()
        self.assertNotIn("locked_pages", [x["id"] for x in ch["blocking"]])
        self.assertTrue(ch["can_commit"], ch["blocking"])
        st, res = self.commit("Raise free delivery to AED 200", ch["paths_digest"])
        self.assertEqual(st, 200, res)
        self.assertEqual(self.head(), res["sha"])
        self.assertIn("flow/checkout.html",
                      git(b.repo, "show", "--name-only", "--format=", res["sha"]).split("\n"))

    def test_commit_takes_only_admin_paths(self):
        b = self.b
        new = self.price("be-mine", 5)
        readme = b.repo / "admin" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nA local note.\n", encoding="utf-8")
        (b.repo / "notes.txt").write_text("scratch\n", encoding="utf-8")
        ch = self.changes()
        groups = ch["groups"]
        self.assertEqual([i["path"] for i in groups["content"]], ["flow/content/products.json"])
        self.assertIn("flow/assets/catalogue.js", [i["path"] for i in groups["generated"]])
        self.assertEqual(sorted(i["path"] for i in groups["other"]), ["admin/README.md", "notes.txt"])
        self.assertEqual(groups["code"], [])
        self.assertTrue(ch["can_commit"], ch["blocking"])
        texts = [e["text"] for d in ch["described"] for e in d["entries"]]
        self.assertEqual(texts, ["Be Mine: price AED %d to AED %d" % (new - 5, new)])
        self.assertEqual(ch["suggested_message"], "Change the price of Be Mine to AED %d" % new)
        st, res = self.commit(ch["suggested_message"], ch["paths_digest"])
        self.assertEqual(st, 200, res)
        self.assertEqual(self.head(), res["sha"])
        committed = git(b.repo, "show", "--name-only", "--format=", res["sha"]).split("\n")
        self.assertIn("flow/content/products.json", committed)
        for p in committed:
            self.assertIn(publishing.group_of(p), publishing.ADMIN_GROUPS, p)
        self.assertEqual(git(b.repo, "log", "-1", "--format=%B", res["sha"]), ch["suggested_message"])
        dirty = git(b.repo, "status", "--porcelain", "--untracked-files=all")
        self.assertIn("admin/README.md", dirty)
        self.assertIn("notes.txt", dirty)
        self.assertNotIn("flow/", dirty)
        self.assertEqual(res["left"], [])
        st, log = b.api("GET", "publish/log")
        self.assertEqual((log["items"][0]["kind"], log["items"][0]["sha"]), ("commit", res["sha"]))
        self.assertFalse(self.changes()["can_commit"])

    def test_message_rules(self):
        self.price("vibe", 1)
        ch = self.changes()
        head = self.head()
        for bad in ("x" * 73, "Change Vibe " + chr(0x2014) + " again", "Change Vibe\n\nCo-Authored-By: someone <a@b.c>",
                    "Change Vibe\n\nSigned-off-by: someone", "Change Vibe\n\nGenerated with a tool", "", "-- Vibe"):
            st, res = self.commit(bad, ch["paths_digest"])
            self.assertEqual(st, 422, (bad, res))
            self.assertEqual(res["error"]["code"], "validation")
        self.assertEqual(self.head(), head)

    def test_dirty_code_blocks_the_commit(self):
        b = self.b
        self.price("vibe", 3)
        with open(str(b.repo / "flow" / "assets" / "shop.js"), "a", encoding="utf-8") as f:
            f.write("\n// a developer's unfinished edit\n")
        ch = self.changes()
        self.assertEqual([i["path"] for i in ch["groups"]["code"]], ["flow/assets/shop.js"])
        self.assertIn("code", [c["id"] for c in ch["blocking"]])
        self.assertFalse(ch["can_commit"])
        head = self.head()
        st, res = self.commit("Change the price of Vibe", ch["paths_digest"])
        self.assertEqual(st, 422, res)
        self.assertEqual(res["error"]["code"], "checks_failed")
        self.assertEqual(self.head(), head)

    def test_a_save_after_the_review_gives_409(self):
        self.price("vibe", 2)
        ch = self.changes()
        self.price("vibe", 1)                      # a save in another tab
        head = self.head()
        st, res = self.commit("Change the price of Vibe", ch["paths_digest"])
        self.assertEqual(st, 409, res)
        self.assertEqual(res["error"]["code"], "changes_moved")
        self.assertEqual(self.head(), head)

    def test_clean_room_catches_a_stale_generated_file(self):
        b = self.b
        # The content edited by hand and the pages not rebuilt: the deploys'
        # own rebuild would differ, so nothing may be committed.
        p = b.repo / "flow" / "content" / "products.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["vibe"]["price"] += 7
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        head = self.head()
        ch = self.changes()
        self.assertEqual([i["path"] for i in ch["groups"]["content"]], ["flow/content/products.json"])
        self.assertEqual(ch["groups"]["generated"], [])
        st, res = self.commit("Change the price of Vibe", ch["paths_digest"])
        self.assertEqual(st, 422, res)
        self.assertEqual(res["error"]["code"], "checks_failed")
        check = res["error"]["details"]["checks"][0]
        self.assertEqual(check["id"], "clean_room")
        self.assertIn("flow/assets/catalogue.js", check["paths"])
        self.assertEqual(self.head(), head)
        verify = b.repo / "flow" / "content" / ".backups" / "verify"
        self.assertEqual(list(verify.iterdir()) if verify.exists() else [], [])
        # a generated file changed by hand is caught the same way
        git(b.repo, "checkout", "-q", "--", ".")
        page = b.repo / "flow" / "index.html"
        page.write_text(page.read_text(encoding="utf-8") + "<!-- by hand -->\n", encoding="utf-8")
        ch = self.changes()
        st, res = self.commit("Change the homepage", ch["paths_digest"])
        self.assertEqual(st, 422, res)
        self.assertEqual(res["error"]["details"]["checks"][0]["paths"], ["flow/index.html"])

    def test_push_is_refused_with_no_push(self):
        st, res = self.b.api("POST", "publish/push", {"preview_id": "1.x", "local_sha": "a" * 40, "remote_sha": "b" * 40,
                                                      "confirm": "PUBLISH", "include_external": True})
        self.assertEqual(st, 403, res)
        self.assertEqual(res["error"]["code"], "no_push")
        self.assertEqual(git(self.b.remote, "rev-parse", "main"), self.b.base)

    def test_fetch_preview_and_no_push(self):
        b = self.b
        new = self.price("amore", 4)
        ch = self.changes()
        st, res = self.commit(ch["suggested_message"], ch["paths_digest"])
        self.assertEqual(st, 200, res)
        # a developer's commit from the terminal rides along
        note = b.repo / "admin" / "docs" / "NOTE-TEST.md"
        note.write_text("A note.\n", encoding="utf-8")
        git(b.repo, "add", "--", "admin/docs/NOTE-TEST.md")
        git(b.repo, "commit", "-q", "-m", "Add a test note")
        st, pv = b.api("GET", "publish/preview")
        self.assertEqual(st, 200, pv)
        self.assertFalse({c["id"]: c for c in pv["checks"]}["fetched"]["ok"])
        self.assertIsNone(pv["preview_id"])
        st, f = b.api("POST", "publish/fetch", {})
        self.assertEqual(st, 200, f)
        remote = git(b.remote, "rev-parse", "main")
        self.assertEqual(f["remote_sha"], remote)
        st, pv = b.api("GET", "publish/preview")
        self.assertEqual(st, 200, pv)
        by = {c["id"]: c for c in pv["checks"]}
        for cid in ("branch", "fetched", "ancestor", "ahead", "clean_room", "dash", "local_ref", "admin_folder",
                    "types", "size", "secrets"):
            self.assertTrue(by[cid]["ok"], by[cid])
        made = {c["subject"]: c["made_in_admin"] for c in pv["commits"]}
        self.assertTrue(made[res["subject"]])
        self.assertFalse(made["Add a test note"])
        self.assertEqual(pv["external"], 1)
        self.assertIn("flow/assets/catalogue.js", [f["path"] for f in pv["published_files"]["code"]])
        self.assertIn("admin/docs/NOTE-TEST.md", [r["path"] for r in pv["riding_along"]])
        texts = [e["text"] for d in pv["semantic"] for e in d["entries"]]
        self.assertIn("Amore: price AED %d to AED %d" % (new - 4, new), texts)
        self.assertTrue(pv["preview_id"])
        st, out = b.api("POST", "publish/push", {"preview_id": pv["preview_id"], "local_sha": pv["local_sha"],
                                                 "remote_sha": pv["remote_sha"], "confirm": "PUBLISH",
                                                 "include_external": True})
        self.assertEqual(st, 403, out)
        self.assertEqual(git(b.remote, "rev-parse", "main"), remote)


class PartitionTests(unittest.TestCase):
    """The group a changed path falls in decides whether a commit takes it."""

    def test_groups(self):
        cases = {"flow/content/products.json": "content", "flow/assets/img/example.jpg": "media",
                 "flow/assets/video/example.mp4": "media", "flow/index.html": "generated",
                 "flow/assets/catalogue.js": "generated", "flow/favicon.ico": "generated",
                 "flow/assets/img/apple-touch-icon.png": "generated", "flow/assets/shop.js": "code",
                 "flow/build.py": "code", "flow/edp_data.json": "code", "flow/tools/make_favicon.py": "other",
                 "flow/assets/img/notes.txt": "other", "admin/README.md": "other"}
        for path, group in cases.items():
            self.assertEqual(publishing.group_of(path), group, path)


class PushTests(unittest.TestCase):
    """gitops.push and publishing.go_live, called directly (no server), on a
    tiny repository whose origin is a throwaway bare repository. The tests
    run in name order: each builds on the history the one before left."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgsadmin-push-"))
        cls.remote = cls.tmp / "remote.git"
        cls.repo = cls.tmp / "repo"
        subprocess.run(["git", "init", "-q", "--bare", str(cls.remote)], check=True)
        subprocess.run(["git", "init", "-q", str(cls.repo)], check=True)
        git(cls.repo, "checkout", "-q", "-b", "main")
        identity(cls.repo)
        cls.write(cls.repo, "first")
        git(cls.repo, "remote", "add", "origin", str(cls.remote))
        git(cls.repo, "push", "-q", "origin", "main")         # seeds the throwaway bare repository
        git(cls.repo, "fetch", "-q", "origin")
        cls.cfg = Config(cls.repo)
        cls.argvs = []
        cls.real_spawn = gitops._spawn

        def spy(cmd, cwd, env, timeout):
            cls.argvs.append(list(cmd))
            return cls.real_spawn(cmd, cwd, env, timeout)
        gitops._spawn = spy

    @classmethod
    def tearDownClass(cls):
        gitops._spawn = cls.real_spawn
        shutil.rmtree(str(cls.tmp), ignore_errors=True)

    @staticmethod
    def write(repo, text):
        (repo / "note.txt").write_text(text + "\n", encoding="utf-8")
        git(repo, "add", "note.txt")
        git(repo, "commit", "-q", "-m", "Write " + text)
        return git(repo, "rev-parse", "HEAD")

    def remote_main(self):
        return git(self.remote, "rev-parse", "main")

    def test_1_fast_forward(self):
        sha = self.write(self.repo, "second")
        res = gitops.push(self.cfg, sha)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.remote_main(), sha)
        self.assertEqual(res["argv"], ["push", "--porcelain", "--no-tags", "origin", sha + ":refs/heads/main"])

    def test_2_the_reviewed_sha_goes_not_the_branch(self):
        reviewed = self.write(self.repo, "third")
        self.write(self.repo, "fourth")            # main moves on after the review
        res = gitops.push(self.cfg, reviewed)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.remote_main(), reviewed)

    def test_3_go_live_checks_again_before_pushing(self):
        app = types.SimpleNamespace(cfg=self.cfg, token="test-token", store=types.SimpleNamespace(actor="test"))
        remote = gitops.fetch(self.cfg)
        local = gitops.resolve(self.cfg, "HEAD")
        self.assertEqual(remote, self.remote_main())
        lines = []
        with self.assertRaises(ApiError) as e:          # GitHub is not where the review saw it
            publishing.go_live(app, local, git(self.repo, "rev-parse", "HEAD~3"), True, lines.append)
        self.assertEqual((e.exception.status, e.exception.code), (412, "review_stale"))
        with self.assertRaises(ApiError) as e:          # "fourth" was made outside the admin
            publishing.go_live(app, local, remote, False, lines.append)
        self.assertEqual((e.exception.status, e.exception.code), (422, "confirm_external"))
        self.assertEqual(self.remote_main(), remote)
        out = publishing.go_live(app, local, remote, True, lines.append)
        self.assertTrue(out["confirmed"], out)
        self.assertEqual(self.remote_main(), local)
        self.assertEqual(out["message"], "Netlify and GitHub Pages have started deploying.")
        self.assertEqual(publishing.read_log(self.cfg)[-1]["kind"], "publish")

    def test_4_a_diverged_remote_is_refused(self):
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(other)], check=True)
        identity(other)
        theirs = self.write(other, "someone else's")
        git(other, "push", "-q", "origin", "main")        # to the throwaway bare repository only
        mine = self.write(self.repo, "fifth")
        res = gitops.push(self.cfg, mine)
        self.assertFalse(res["ok"], res)
        self.assertEqual(self.remote_main(), theirs)
        self.assertTrue(any(r["flag"] == "!" for r in res["refs"]), res)
        self.assertIn("nothing was published", publishing.push_failure(res))

    def test_5_no_force_argument_ever(self):
        pushes = [a[a.index("push"):] for a in self.argvs if "push" in a]
        self.assertGreaterEqual(len(pushes), 4)
        for argv in pushes:
            self.assertEqual(argv[:4], ["push", "--porcelain", "--no-tags", "origin"])
            self.assertEqual(len(argv), 5)
            self.assertRegex(argv[4], r"^[0-9a-f]{40}:refs/heads/main$")
            for a in argv:
                self.assertFalse(a.startswith("+") or a.startswith("--force") or a in gitops.PUSH_REFUSED, a)
        for bad in ("--force", "-f", "--force-with-lease", "--force-with-lease=main", "--mirror", "--delete", "-d",
                    "--prune", "-fq", "+%s:refs/heads/main" % ("a" * 40), ":refs/heads/main"):
            with self.assertRaises(ValueError):
                gitops.check_push_args(["push", bad])
        for bad in ("main", "HEAD", "a" * 39, "+" + "a" * 40, "A" * 40, None):
            with self.assertRaises(ApiError):
                gitops.push_argv(bad)
        with self.assertRaises(ValueError):
            gitops.run(self.cfg, ["push", "origin"])
        with self.assertRaises(ValueError):
            gitops.write(self.cfg, ["commit", "--amend", "--only", "-m", "x", "--", "note.txt"])
