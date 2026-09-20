"use strict";

(function () {
  const root = document.querySelector("[data-case-builder]");
  if (!root) return;

  const draft = document.getElementById("case-note-draft");
  const addButton = document.getElementById("case-note-add");
  const emptyState = document.getElementById("case-notes-empty");
  const notesList = document.getElementById("case-notes-list");
  const status = document.getElementById("case-builder-status");
  const discardLink = document.getElementById("case-builder-discard");
  let nextLocalId = 1;

  function timestamp() {
    return new Date().toISOString();
  }

  function createAudit(createdAt = timestamp()) {
    return {
      createdAt,
      updatedAt: createdAt,
      revision: 1,
    };
  }

  function createWorkspace() {
    return {
      schemaVersion: 1,
      audit: createAudit(),
      notes: [],
      claims: [],
      timelineEvents: [],
      evidenceItems: [],
      corroborators: [],
      gapsAndRisks: [],
      relationships: [],
      narrativeDrafts: [],
      sharePlan: {
        audit: createAudit(),
        selectedItems: [],
      },
    };
  }

  let workspace = createWorkspace();

  function updateAudit(audit) {
    audit.updatedAt = timestamp();
    audit.revision += 1;
  }

  function announce(message) {
    status.textContent = "";
    window.requestAnimationFrame(function () {
      status.textContent = message;
    });
  }

  function configureSensitiveTextarea(textarea) {
    textarea.autocomplete = "off";
    textarea.autocapitalize = "off";
    textarea.setAttribute("autocorrect", "off");
    textarea.spellcheck = false;
    textarea.translate = false;
  }

  function createButton(label, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    if (className) button.className = className;
    button.addEventListener("click", handler);
    return button;
  }

  function beginEdit(note, item) {
    const label = document.createElement("label");
    const editorId = `case-note-edit-${note.id}`;
    label.htmlFor = editorId;
    label.className = "visually-hidden";
    label.textContent = "Edit note";

    const editor = document.createElement("textarea");
    editor.id = editorId;
    editor.rows = 8;
    editor.value = note.text;
    configureSensitiveTextarea(editor);

    const actions = document.createElement("div");
    actions.className = "case-note-actions";
    actions.append(
      createButton("Save", "", function () {
        const text = editor.value.trim();
        if (!text) {
          announce("Enter note text before saving.");
          editor.focus();
          return;
        }
        note.text = text;
        updateAudit(note.audit);
        updateAudit(workspace.audit);
        renderNotes();
        announce("Note updated.");
        focusNoteAction(note.id, "Edit");
      }),
      createButton("Cancel", "btn", function () {
        renderNotes();
        announce("Edit canceled.");
        focusNoteAction(note.id, "Edit");
      }),
    );

    item.replaceChildren(label, editor, actions);
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  }

  function requestDelete(note, actions) {
    const prompt = document.createElement("span");
    prompt.id = `case-note-delete-prompt-${note.id}`;
    prompt.className = "case-note-delete-prompt";
    prompt.textContent = "Delete this note from the open page?";

    const confirmButton = createButton("Confirm delete", "btn-danger", function () {
      const noteIndex = workspace.notes.findIndex(function (candidate) {
        return candidate.id === note.id;
      });
      if (noteIndex === -1) return;

      workspace.notes[noteIndex].text = "";
      workspace.notes.splice(noteIndex, 1);
      updateAudit(workspace.audit);
      renderNotes();
      announce("Note deleted from the open page.");
      addButton.focus();
    });
    confirmButton.setAttribute("aria-describedby", prompt.id);

    actions.replaceChildren(
      prompt,
      confirmButton,
      createButton("Cancel", "btn", function () {
        renderNotes();
        announce("Delete canceled.");
        focusNoteAction(note.id, "Delete");
      }),
    );
    confirmButton.focus();
  }

  function renderNotes() {
    notesList.replaceChildren();
    emptyState.hidden = workspace.notes.length !== 0;

    workspace.notes.forEach(function (note) {
      const item = document.createElement("li");
      item.className = "case-note-card";
      item.dataset.noteId = note.id;

      const text = document.createElement("p");
      text.className = "case-note-text";
      text.textContent = note.text;

      const actions = document.createElement("div");
      actions.className = "case-note-actions";
      actions.append(
        createButton("Edit", "btn", function () {
          beginEdit(note, item);
        }),
        createButton("Delete", "btn-danger", function () {
          requestDelete(note, actions);
        }),
      );

      item.append(text, actions);
      notesList.appendChild(item);
    });
  }

  function focusNoteAction(noteId, label) {
    const item = Array.from(notesList.children).find(function (candidate) {
      return candidate.dataset.noteId === noteId;
    });
    if (!item) return;

    const button = Array.from(item.querySelectorAll("button")).find(function (candidate) {
      return candidate.textContent === label;
    });
    if (button) button.focus();
  }

  function addNote() {
    const text = draft.value.trim();
    if (!text) {
      announce("Enter note text before adding it.");
      draft.focus();
      return;
    }

    const id = `note-${nextLocalId}`;
    nextLocalId += 1;
    workspace.notes.push({
      id,
      audit: createAudit(),
      review: {
        uncertainty: "unmarked",
        sensitivity: "unmarked",
      },
      disposition: "active",
      text,
    });
    updateAudit(workspace.audit);
    draft.value = "";
    renderNotes();
    announce("Note added to the open page.");
    draft.focus();
  }

  function clearWorkspace() {
    if (workspace) {
      workspace.notes.forEach(function (note) {
        note.text = "";
      });
      workspace.notes.length = 0;
    }
    workspace = null;
    draft.value = "";
    notesList.querySelectorAll("textarea").forEach(function (editor) {
      editor.value = "";
    });
    status.textContent = "";
    notesList.replaceChildren();
    emptyState.hidden = false;
  }

  addButton.addEventListener("click", addNote);
  discardLink.addEventListener("click", clearWorkspace);
  window.addEventListener("pagehide", clearWorkspace);
  window.addEventListener("pageshow", function () {
    if (!workspace) {
      workspace = createWorkspace();
      nextLocalId = 1;
      renderNotes();
    }
  });

  renderNotes();
})();
