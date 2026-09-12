// One editing screen: the copy the server has, the draft being edited, the
// save bar while they differ, and every way a save can end (saved and
// rebuilt, a field to fix, a build that failed and was put back, a version
// changed elsewhere, a restarted server).
import { api } from "./api.js";
import { h, clear, copy, same } from "./dom.js";
import { savebar, toast, banner, choiceDialog, guard, onSaveKey, announce } from "./ui.js";
import { makeCtx, showErrors, clearErrors } from "./forms.js";

export function mountEditor(main, app, opts) {
  let server = null;
  let draft = null;
  let ctx = null;
  const head = h("div", { class: "page-head" });
  const msgs = h("div", { class: "msgs" });
  const body = h("div", { class: "editor" });
  clear(main).append(head, msgs, body);

  const dirty = () => !!server && !same(draft, server.data);
  const update = () => (dirty() ? savebar.show({ onSave: save, onDiscard: discard }) : savebar.hide());
  guard.set(dirty);
  onSaveKey(save);

  function drawHead() {
    clear(head).append(
      h("div", {},
        opts.back ? h("a", { class: "back", href: opts.back.href }, opts.back.label) : null,
        h("h1", { tabindex: "-1" }, typeof opts.heading === "function" ? opts.heading(draft) : opts.heading),
        opts.subtitle ? h("p", { class: "sub" }, opts.subtitle) : null),
      h("div", { class: "head-actions" }, opts.actions ? opts.actions(api_) : null));
  }

  function draw() {
    const keep = ctx ? ctx.confirmed : new Set();
    ctx = makeCtx(app, { onChange: update, rerender: draw, confirmed: keep });
    drawHead();
    clear(body).append(opts.form(ctx, draft, server.meta || {}));
  }

  async function reload() {
    const r = await opts.load();
    server = r;
    draft = copy(r.data);
    if (ctx) ctx.confirmed = new Set();
    draw();
    update();
  }

  function discard() {
    draft = copy(server.data);
    if (ctx) ctx.confirmed = new Set();
    clear(msgs);
    draw();
    update();
    announce("Changes discarded.");
  }

  async function save() {
    if (!dirty()) return;
    clearErrors(ctx);
    clear(msgs);
    savebar.busy("Saving and rebuilding the site");
    try {
      const res = await opts.put(draft, server.rev, [...ctx.confirmed]);
      server = { rev: res.rev, data: res.data, meta: server.meta };
      draft = copy(res.data);
      ctx.confirmed = new Set();
      savebar.hide();
      draw();
      if (opts.onSaved) opts.onSaved(res);
      const secs = res.build && res.build.ms ? (res.build.ms / 1000).toFixed(1) : null;
      toast(secs ? "Saved. The site rebuilt in " + secs + " s." : "Saved.",
        opts.view ? { action: { label: "View on store", href: opts.view(res.data), external: true } } : {});
      if (res.warnings && res.warnings.length) {
        msgs.append(banner({ tone: "warning", title: "Saved. Something to check:", items: res.warnings.map((w) => w.message) }));
      }
    } catch (e) {
      await failed(e);
    }
  }

  async function failed(e) {
    update();
    if (e.code === "validation") {
      const rest = showErrors(ctx, e.details);
      msgs.append(banner({ tone: "critical", title: "Not saved: some fields need attention.", items: rest.length ? rest : ["The fields are marked below."] }));
    } else if (e.code === "build_failed") {
      msgs.append(banner({ tone: "critical", title: "Your change was not applied: the site would not build with it.",
        items: ((e.details && e.details.problems) || []).concat(["Everything was put back as it was. Your edits are still here to fix."]) }));
    } else if (e.code === "stale_rev") {
      const pick = await choiceDialog({
        title: "This changed since you opened it",
        body: ["It was saved somewhere else in the meantime: another tab, a terminal or a Claude session."],
        choices: [{ label: "Keep editing", value: "keep" }, { label: "Take theirs", value: "theirs" }, { label: "Save mine over it", value: "mine", primary: true }],
      });
      if (pick === "theirs") await reload();
      else if (pick === "mine" && e.details) {
        server = { rev: e.details.current_rev, data: e.details.current, meta: server.meta };
        // A screen that edits part of a document lays that part over the
        // newer copy, so the rest keeps what was saved in the meantime.
        if (opts.rebase) {
          draft = opts.rebase(copy(e.details.current), draft);
          draw();
          update();
        }
        await save();
      }
    } else if (e.code === "bad_token") {
      msgs.append(banner({ tone: "critical", title: "The admin restarted.", items: ["Reload the page to carry on. Unsaved changes on this screen will be lost."],
        actions: [h("button", { class: "btn", type: "button", onclick: () => location.reload() }, "Reload")] }));
    } else if (e.code === "busy") {
      toast("Another change is still saving. Try again in a moment.");
    } else {
      msgs.append(banner({ tone: "critical", title: e.message }));
    }
  }

  const api_ = {
    rev: () => server && server.rev,
    data: () => server && server.data,
    draft: () => draft,
    reload, save, msgs,
  };
  reload().catch((e) => {
    clear(body).append(banner({ tone: "critical", title: e.message }));
  });
  return api_;
}

export { api };
