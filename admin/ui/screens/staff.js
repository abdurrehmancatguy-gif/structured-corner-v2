// Staff: who may open the admin, and what each of them may do. Admin only.
//
// The list is the whole gate: an address that is not on it is refused after
// signing in, whatever account it holds. The server checks all of this again
// (bgsadmin/api/staff.py) and refuses a change that would remove or demote
// the person making it, or leave nobody in charge; the screen only tries to
// make those refusals unnecessary.
import { api } from "../lib/api.js";
import { h, clear, useCss } from "../lib/dom.js";
import { icon } from "../icons.js";
import { banner, toast, guard, savebar, announce, onSaveKey, formDialog } from "../lib/ui.js";

const EMAIL = /^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$/;

export async function render(main, { app }) {
  useCss("staff");
  const note = h("div", { class: "msgs" });
  const body = h("div", { class: "table-wrap" });
  const head = h("div", { class: "page-head" }, h("div", {},
    h("h1", { tabindex: "-1" }, "Staff"),
    h("p", { class: "sub" }, "Who may open the admin, and what each of them may do. Everyone else is refused, "
      + "however valid their account.")));

  clear(main).append(head, note, h("section", { class: "card flush" }, body));

  let people = [];
  let roles = [];
  let me = "";
  let saving = false;

  try {
    const got = await api("GET", "staff");
    people = got.people.map((p) => ({ email: p.email, role: p.role }));
    roles = got.roles;
    me = got.me || "";
  } catch (e) {
    return clear(note).append(banner({ tone: "critical", title: e.message }));
  }

  // what the list looked like when it was last saved, so the save bar goes
  // once a change is in and comes back on the next edit
  let saved = JSON.stringify(people);
  const dirty = () => JSON.stringify(people) !== saved;

  function roleSelect(person) {
    return h("select", {
      class: "input", "aria-label": "Role for " + person.email,
      disabled: person.email === me ? "disabled" : null,
      title: person.email === me ? "You cannot change your own role. Ask another Admin." : null,
      onchange: (e) => { person.role = e.target.value; changed(); },
    }, roles.map((r) => h("option", { value: r.role, selected: r.role === person.role ? "selected" : null }, r.label)));
  }

  function row(person) {
    const yours = person.email === me;
    return h("tr", {},
      h("td", {}, h("span", { class: "mono" }, person.email), yours ? h("span", { class: "pill" }, "you") : null),
      h("td", {}, roleSelect(person)),
      h("td", { class: "what" }, (roles.find((r) => r.role === person.role) || {}).what || ""),
      h("td", { class: "right" }, yours ? null : h("button", {
        class: "btn ghost danger-text", type: "button",
        onclick: () => { people = people.filter((p) => p !== person); draw(); changed(); },
      }, icon("trash", 16), "Remove")));
  }

  const emailBox = h("input", { class: "input", type: "email", placeholder: "someone@example.com",
                                "aria-label": "New person's email" });
  const newRole = h("select", { class: "input", "aria-label": "Role for the new person" });

  function addPerson() {
    const email = emailBox.value.trim().toLowerCase();
    if (!EMAIL.test(email)) {
      return clear(note).append(banner({ tone: "critical", title: "That is not an email address." }));
    }
    if (people.some((p) => p.email === email)) {
      return clear(note).append(banner({ tone: "critical", title: email + " is already on the list." }));
    }
    clear(note);
    people = people.concat([{ email, role: newRole.value || "inventory" }]);
    emailBox.value = "";
    draw();
    changed();
  }

  function draw() {
    clear(newRole).append(...roles.map((r) => h("option", { value: r.role,
      selected: r.role === "inventory" ? "selected" : null }, r.label)));
    clear(body).append(
      h("table", { class: "table staff" },
        h("thead", {}, h("tr", {},
          h("th", {}, "Address"), h("th", {}, "Role"), h("th", {}, "What that means"), h("th", {}))),
        h("tbody", {}, people.map(row))),
      h("div", { class: "addrow" },
        emailBox, newRole,
        h("button", { class: "btn", type: "button", onclick: addPerson }, icon("plus", 16), "Add person")),
      h("p", { class: "hint" },
        "A change takes effect at once: someone removed here is refused on their next click, without "
        + "signing out. Every change is written to the log with your name and your reason."));
  }

  async function save() {
    if (saving) return;
    const answer = await formDialog({
      title: "Why is this changing?",
      body: "A few words, kept in the log beside your name. A role change is read back long after it is made.",
      confirm: "Save",
      fields: [{ name: "reason", label: "Reason", required: true,
                 placeholder: "new stock assistant, left the company, promoted to manager" }],
    });
    if (!answer) return;
    const reason = answer.reason || "";
    if (reason.trim().length < 3) {
      return clear(note).append(banner({ tone: "critical", title: "Say why this changes, in a few words." }));
    }
    saving = true;
    savebar.busy("Saving");
    try {
      const res = await api("PUT", "staff", { people, reason: reason.trim() });
      people = res.people.map((p) => ({ email: p.email, role: p.role }));
      saved = JSON.stringify(people);
      guard.clear();
      savebar.hide();
      draw();
      clear(note);
      toast(res.changed.length ? "Saved. " + res.changed.length + " change" + (res.changed.length === 1 ? "" : "s")
                               : "Nothing to change.");
      announce("Staff saved");
    } catch (e) {
      clear(note).append(banner({ tone: "critical", title: e.message }));
    } finally {
      saving = false;
    }
  }

  function changed() {
    if (dirty()) {
      guard.set(dirty);
      savebar.show({ onSave: save, onDiscard: () => { location.reload(); },
                     message: "People and roles not saved" });
    } else {
      guard.clear();
      savebar.hide();
    }
  }

  onSaveKey(save);
  draw();
}
