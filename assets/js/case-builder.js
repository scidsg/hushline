"use strict";

(function () {
  const root = document.querySelector("[data-case-builder]");
  if (!root) return;

  const status = document.getElementById("case-builder-status");
  const discardLink = document.getElementById("case-builder-discard");
  const draft = document.getElementById("case-note-draft");
  const addNoteButton = document.getElementById("case-note-add");
  const claimSummary = document.getElementById("case-claim-summary");
  const claimKind = document.getElementById("case-claim-kind");
  const claimUncertain = document.getElementById("case-claim-uncertain");
  const addClaimButton = document.getElementById("case-claim-add");
  const eventDate = document.getElementById("case-event-date");
  const eventApproximate = document.getElementById("case-event-approximate");
  const eventSummary = document.getElementById("case-event-summary");
  const eventParties = document.getElementById("case-event-parties");
  const eventSources = document.getElementById("case-event-sources");
  const addEventButton = document.getElementById("case-event-add");
  const evidenceTitle = document.getElementById("case-evidence-title-input");
  const evidenceDescription = document.getElementById("case-evidence-description");
  const evidenceLocation = document.getElementById("case-evidence-location");
  const evidenceMissing = document.getElementById("case-evidence-missing");
  const evidenceUncertain = document.getElementById("case-evidence-uncertain");
  const evidenceRisky = document.getElementById("case-evidence-risky");
  const addEvidenceButton = document.getElementById("case-evidence-add");
  const corroboratorLabel = document.getElementById("case-corroborator-label");
  const corroboratorBasis = document.getElementById("case-corroborator-basis");
  const corroboratorUncertain = document.getElementById("case-corroborator-uncertain");
  const addCorroboratorButton = document.getElementById("case-corroborator-add");
  const connectionFrom = document.getElementById("case-connection-from");
  const connectionType = document.getElementById("case-connection-type");
  const connectionTo = document.getElementById("case-connection-to");
  const addConnectionButton = document.getElementById("case-connection-add");

  const views = {
    notes: {
      empty: document.getElementById("case-notes-empty"),
      list: document.getElementById("case-notes-list"),
    },
    claims: {
      empty: document.getElementById("case-claims-empty"),
      list: document.getElementById("case-claims-list"),
    },
    timelineEvents: {
      empty: document.getElementById("case-timeline-empty"),
      list: document.getElementById("case-timeline-list"),
    },
    evidenceItems: {
      empty: document.getElementById("case-evidence-empty"),
      list: document.getElementById("case-evidence-list"),
    },
    corroborators: {
      empty: document.getElementById("case-corroborators-empty"),
      list: document.getElementById("case-corroborators-list"),
    },
    relationships: {
      empty: document.getElementById("case-connections-empty"),
      list: document.getElementById("case-connections-list"),
    },
  };

  const collectionNames = {
    claim: "claims",
    event: "timelineEvents",
    evidence: "evidenceItems",
    corroborator: "corroborators",
    connection: "relationships",
  };

  const itemTypeLabels = {
    claim: "Claim",
    event: "Event",
    evidence: "Evidence",
    corroborator: "Corroborator",
  };

  const relationshipLabels = {
    supports: "supports",
    "source-for": "is a source for",
    corroborates: "corroborates",
    "context-for": "provides context for",
    contradicts: "may contradict",
  };

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

  function nextId(prefix) {
    const id = `${prefix}-${nextLocalId}`;
    nextLocalId += 1;
    return id;
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

  function addText(container, className, value) {
    if (!value) return;
    const paragraph = document.createElement("p");
    paragraph.className = className;
    paragraph.textContent = value;
    container.appendChild(paragraph);
  }

  function addLabeledText(container, label, value) {
    if (!value) return;
    const paragraph = document.createElement("p");
    paragraph.className = "case-record-detail";
    const heading = document.createElement("strong");
    heading.textContent = `${label}: `;
    paragraph.append(heading, document.createTextNode(value));
    container.appendChild(paragraph);
  }

  function addMarkers(container, markers) {
    const visibleMarkers = markers.filter(Boolean);
    if (!visibleMarkers.length) return;

    const list = document.createElement("ul");
    list.className = "case-record-markers";
    list.setAttribute("aria-label", "Markers");
    visibleMarkers.forEach(function (marker) {
      const item = document.createElement("li");
      item.textContent = marker;
      list.appendChild(item);
    });
    container.appendChild(list);
  }

  function scrub(value) {
    if (!value || typeof value !== "object") return;
    Object.keys(value).forEach(function (key) {
      if (typeof value[key] === "string") {
        value[key] = "";
      } else {
        scrub(value[key]);
      }
    });
  }

  function removeRelationshipsFor(itemId) {
    for (let index = workspace.relationships.length - 1; index >= 0; index -= 1) {
      const relationship = workspace.relationships[index];
      if (relationship.fromId === itemId || relationship.toId === itemId) {
        scrub(relationship);
        workspace.relationships.splice(index, 1);
      }
    }
  }

  function requestDelete(record, recordType, actions, returnControl) {
    const prompt = document.createElement("span");
    prompt.id = `case-delete-prompt-${record.id}`;
    prompt.className = "case-record-delete-prompt";
    prompt.textContent = `Delete this ${recordType} from the open page?`;

    const confirmButton = createButton("Confirm delete", "btn-danger", function () {
      const collectionName = collectionNames[recordType];
      const collection = workspace[collectionName];
      const index = collection.findIndex(function (candidate) {
        return candidate.id === record.id;
      });
      if (index === -1) return;

      if (recordType !== "connection") removeRelationshipsFor(record.id);
      scrub(collection[index]);
      collection.splice(index, 1);
      updateAudit(workspace.audit);
      renderWorkspace();
      announce(`${itemTypeLabels[recordType] || "Connection"} deleted from the open page.`);
      returnControl.focus();
    });
    confirmButton.setAttribute("aria-describedby", prompt.id);

    actions.replaceChildren(
      prompt,
      confirmButton,
      createButton("Cancel", "btn", function () {
        renderWorkspace();
        announce("Delete canceled.");
      }),
    );
    confirmButton.focus();
  }

  function addDeleteAction(card, record, recordType, returnControl) {
    const actions = document.createElement("div");
    actions.className = "case-record-actions";
    actions.appendChild(
      createButton("Delete", "btn-danger", function () {
        requestDelete(record, recordType, actions, returnControl);
      }),
    );
    card.appendChild(actions);
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
    actions.className = "case-record-actions";
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
        renderWorkspace();
        announce("Note updated.");
        focusNoteAction(note.id, "Edit");
      }),
      createButton("Cancel", "btn", function () {
        renderWorkspace();
        announce("Edit canceled.");
        focusNoteAction(note.id, "Edit");
      }),
    );

    item.replaceChildren(label, editor, actions);
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  }

  function requestNoteDelete(note, actions) {
    const prompt = document.createElement("span");
    prompt.id = `case-note-delete-prompt-${note.id}`;
    prompt.className = "case-record-delete-prompt";
    prompt.textContent = "Delete this note from the open page?";

    const confirmButton = createButton("Confirm delete", "btn-danger", function () {
      const noteIndex = workspace.notes.findIndex(function (candidate) {
        return candidate.id === note.id;
      });
      if (noteIndex === -1) return;

      scrub(workspace.notes[noteIndex]);
      workspace.notes.splice(noteIndex, 1);
      updateAudit(workspace.audit);
      renderWorkspace();
      announce("Note deleted from the open page.");
      addNoteButton.focus();
    });
    confirmButton.setAttribute("aria-describedby", prompt.id);

    actions.replaceChildren(
      prompt,
      confirmButton,
      createButton("Cancel", "btn", function () {
        renderWorkspace();
        announce("Delete canceled.");
        focusNoteAction(note.id, "Delete");
      }),
    );
    confirmButton.focus();
  }

  function renderNotes() {
    const view = views.notes;
    view.list.replaceChildren();
    view.empty.hidden = workspace.notes.length !== 0;

    workspace.notes.forEach(function (note) {
      const item = document.createElement("li");
      item.className = "case-record-card case-note-card";
      item.dataset.noteId = note.id;
      addText(item, "case-note-text", note.text);

      const actions = document.createElement("div");
      actions.className = "case-record-actions";
      actions.append(
        createButton("Edit", "btn", function () {
          beginEdit(note, item);
        }),
        createButton("Delete", "btn-danger", function () {
          requestNoteDelete(note, actions);
        }),
      );
      item.appendChild(actions);
      view.list.appendChild(item);
    });
  }

  function focusNoteAction(noteId, label) {
    const item = Array.from(views.notes.list.children).find(function (candidate) {
      return candidate.dataset.noteId === noteId;
    });
    if (!item) return;

    const button = Array.from(item.querySelectorAll("button")).find(function (candidate) {
      return candidate.textContent === label;
    });
    if (button) button.focus();
  }

  function renderClaims() {
    const view = views.claims;
    view.list.replaceChildren();
    view.empty.hidden = workspace.claims.length !== 0;

    workspace.claims.forEach(function (claim) {
      const item = document.createElement("li");
      item.className = "case-record-card case-claim-card";
      item.dataset.recordId = claim.id;
      const title = document.createElement("h4");
      title.textContent = claim.kind === "core" ? "Core claim" : "Background detail";
      item.appendChild(title);
      addText(item, "case-record-text", claim.summary);
      addMarkers(item, [claim.review.uncertainty === "uncertain" ? "Uncertain" : ""]);
      addDeleteAction(item, claim, "claim", addClaimButton);
      view.list.appendChild(item);
    });
  }

  function renderTimeline() {
    const view = views.timelineEvents;
    view.list.replaceChildren();
    view.empty.hidden = workspace.timelineEvents.length !== 0;
    const orderedEvents = workspace.timelineEvents.slice().sort(function (left, right) {
      return left.date.localeCompare(right.date);
    });
    orderedEvents.forEach(function (event) {
      const item = document.createElement("li");
      item.className = "case-record-card case-event-card";
      item.dataset.recordId = event.id;
      const title = document.createElement("h4");
      title.textContent = `${event.approximate ? "About " : ""}${event.date}`;
      item.appendChild(title);
      addText(item, "case-record-text", event.summary);
      addLabeledText(item, "Parties", event.parties);
      addLabeledText(item, "Source references", event.sourceReferences);
      addMarkers(item, [event.approximate ? "Approximate date" : ""]);
      addDeleteAction(item, event, "event", addEventButton);
      view.list.appendChild(item);
    });
  }

  function renderEvidence() {
    const view = views.evidenceItems;
    view.list.replaceChildren();
    view.empty.hidden = workspace.evidenceItems.length !== 0;
    workspace.evidenceItems.forEach(function (evidence) {
      const item = document.createElement("li");
      item.className = "case-record-card case-evidence-card";
      item.dataset.recordId = evidence.id;
      const title = document.createElement("h4");
      title.textContent = evidence.title;
      item.appendChild(title);
      addText(item, "case-record-text", evidence.description);
      addLabeledText(item, "Known location or custodian", evidence.location);
      addMarkers(item, [
        evidence.availability === "missing" ? "Missing or unavailable" : "Available",
        evidence.review.uncertainty === "uncertain" ? "Uncertain" : "",
        evidence.review.accessRisk === "risky" ? "Risky to access — leave it alone" : "",
      ]);
      addDeleteAction(item, evidence, "evidence", addEvidenceButton);
      view.list.appendChild(item);
    });
  }

  function renderCorroborators() {
    const view = views.corroborators;
    view.list.replaceChildren();
    view.empty.hidden = workspace.corroborators.length !== 0;
    workspace.corroborators.forEach(function (corroborator) {
      const item = document.createElement("li");
      item.className = "case-record-card case-corroborator-card";
      item.dataset.recordId = corroborator.id;
      const title = document.createElement("h4");
      title.textContent = corroborator.label;
      item.appendChild(title);
      addText(item, "case-record-text", corroborator.basis);
      addMarkers(item, [
        corroborator.review.uncertainty === "uncertain" ? "Uncertain" : "",
      ]);
      addDeleteAction(item, corroborator, "corroborator", addCorroboratorButton);
      view.list.appendChild(item);
    });
  }

  function getLinkableRecords() {
    return [
      ...workspace.claims.map(function (record) {
        return { record, type: "claim", label: record.summary };
      }),
      ...workspace.timelineEvents.map(function (record) {
        return { record, type: "event", label: `${record.date}: ${record.summary}` };
      }),
      ...workspace.evidenceItems.map(function (record) {
        return { record, type: "evidence", label: record.title };
      }),
      ...workspace.corroborators.map(function (record) {
        return { record, type: "corroborator", label: record.label };
      }),
    ];
  }

  function recordName(itemId) {
    const match = getLinkableRecords().find(function (item) {
      return item.record.id === itemId;
    });
    if (!match) return "Deleted item";
    return `${itemTypeLabels[match.type]}: ${match.label}`;
  }

  function addConnectionOptions(select, records, placeholder) {
    const placeholderOption = document.createElement("option");
    placeholderOption.value = "";
    placeholderOption.textContent = placeholder;
    select.appendChild(placeholderOption);
    records.forEach(function (item) {
      const recordOption = document.createElement("option");
      recordOption.value = item.record.id;
      const label = `${itemTypeLabels[item.type]}: ${item.label}`;
      recordOption.textContent = label.length > 100 ? `${label.slice(0, 97)}...` : label;
      select.appendChild(recordOption);
    });
  }

  function renderConnectionOptions() {
    const records = getLinkableRecords();
    connectionFrom.replaceChildren();
    connectionTo.replaceChildren();
    addConnectionOptions(connectionFrom, records, "Select an item");
    addConnectionOptions(connectionTo, records, "Select another item");
    addConnectionButton.disabled = records.length < 2;
  }

  function renderRelationships() {
    const view = views.relationships;
    view.list.replaceChildren();
    view.empty.hidden = workspace.relationships.length !== 0;
    workspace.relationships.forEach(function (relationship) {
      const item = document.createElement("li");
      item.className = "case-record-card case-connection-card";
      item.dataset.recordId = relationship.id;
      addText(
        item,
        "case-record-text",
        `${recordName(relationship.fromId)} ${relationshipLabels[relationship.type]} ${recordName(
          relationship.toId,
        )}`,
      );
      addDeleteAction(item, relationship, "connection", addConnectionButton);
      view.list.appendChild(item);
    });
  }

  function renderWorkspace() {
    renderNotes();
    renderClaims();
    renderTimeline();
    renderEvidence();
    renderCorroborators();
    renderRelationships();
    renderConnectionOptions();
  }

  function addNote() {
    const text = draft.value.trim();
    if (!text) {
      announce("Enter note text before adding it.");
      draft.focus();
      return;
    }
    workspace.notes.push({
      id: nextId("note"),
      audit: createAudit(),
      review: { uncertainty: "unmarked", sensitivity: "unmarked" },
      disposition: "active",
      text,
    });
    updateAudit(workspace.audit);
    draft.value = "";
    renderWorkspace();
    announce("Note added to the open page.");
    draft.focus();
  }

  function addClaim() {
    const summary = claimSummary.value.trim();
    if (!summary) {
      announce("Enter a claim or background detail before adding it.");
      claimSummary.focus();
      return;
    }
    workspace.claims.push({
      id: nextId("claim"),
      audit: createAudit(),
      review: { uncertainty: claimUncertain.checked ? "uncertain" : "unmarked" },
      disposition: "active",
      kind: claimKind.value,
      summary,
    });
    updateAudit(workspace.audit);
    claimSummary.value = "";
    claimKind.value = "core";
    claimUncertain.checked = false;
    renderWorkspace();
    announce("Claim added to the open page.");
    claimSummary.focus();
  }

  function addEvent() {
    const date = eventDate.value;
    const summary = eventSummary.value.trim();
    if (!date) {
      announce("Choose a date before adding the event.");
      eventDate.focus();
      return;
    }
    if (!summary) {
      announce("Describe what happened before adding the event.");
      eventSummary.focus();
      return;
    }
    workspace.timelineEvents.push({
      id: nextId("event"),
      audit: createAudit(),
      review: { uncertainty: eventApproximate.checked ? "uncertain" : "unmarked" },
      disposition: "active",
      date,
      approximate: eventApproximate.checked,
      summary,
      parties: eventParties.value.trim(),
      sourceReferences: eventSources.value.trim(),
    });
    updateAudit(workspace.audit);
    eventDate.value = "";
    eventApproximate.checked = false;
    eventSummary.value = "";
    eventParties.value = "";
    eventSources.value = "";
    renderWorkspace();
    announce("Timeline event added and arranged by date.");
    eventDate.focus();
  }

  function addEvidence() {
    const title = evidenceTitle.value.trim();
    if (!title) {
      announce("Enter an evidence label before adding the record.");
      evidenceTitle.focus();
      return;
    }
    workspace.evidenceItems.push({
      id: nextId("evidence"),
      audit: createAudit(),
      review: {
        uncertainty: evidenceUncertain.checked ? "uncertain" : "unmarked",
        accessRisk: evidenceRisky.checked ? "risky" : "unmarked",
      },
      disposition: "active",
      availability: evidenceMissing.checked ? "missing" : "available",
      title,
      description: evidenceDescription.value.trim(),
      location: evidenceLocation.value.trim(),
    });
    updateAudit(workspace.audit);
    evidenceTitle.value = "";
    evidenceDescription.value = "";
    evidenceLocation.value = "";
    evidenceMissing.checked = false;
    evidenceUncertain.checked = false;
    evidenceRisky.checked = false;
    renderWorkspace();
    announce("Evidence record added to the inventory.");
    evidenceTitle.focus();
  }

  function addCorroborator() {
    const label = corroboratorLabel.value.trim();
    const basis = corroboratorBasis.value.trim();
    if (!label) {
      announce("Enter a person or source label before adding the corroborator.");
      corroboratorLabel.focus();
      return;
    }
    if (!basis) {
      announce("Describe what the person or source may corroborate.");
      corroboratorBasis.focus();
      return;
    }
    workspace.corroborators.push({
      id: nextId("corroborator"),
      audit: createAudit(),
      review: { uncertainty: corroboratorUncertain.checked ? "uncertain" : "unmarked" },
      disposition: "active",
      label,
      basis,
    });
    updateAudit(workspace.audit);
    corroboratorLabel.value = "";
    corroboratorBasis.value = "";
    corroboratorUncertain.checked = false;
    renderWorkspace();
    announce("Corroborator added to the open page.");
    corroboratorLabel.focus();
  }

  function addConnection() {
    const fromId = connectionFrom.value;
    const toId = connectionTo.value;
    if (!fromId || !toId) {
      announce("Choose two items before adding a connection.");
      connectionFrom.focus();
      return;
    }
    if (fromId === toId) {
      announce("Choose two different items for a connection.");
      connectionTo.focus();
      return;
    }
    const duplicate = workspace.relationships.some(function (relationship) {
      return (
        relationship.fromId === fromId &&
        relationship.toId === toId &&
        relationship.type === connectionType.value
      );
    });
    if (duplicate) {
      announce("That connection is already mapped.");
      connectionFrom.focus();
      return;
    }
    workspace.relationships.push({
      id: nextId("connection"),
      audit: createAudit(),
      fromId,
      toId,
      type: connectionType.value,
    });
    updateAudit(workspace.audit);
    connectionType.value = "supports";
    renderWorkspace();
    announce("Connection added to the open page.");
    connectionFrom.focus();
  }

  function clearWorkspace() {
    if (workspace) scrub(workspace);
    workspace = null;
    root.querySelectorAll("input, textarea").forEach(function (control) {
      if (control.type === "checkbox") {
        control.checked = false;
      } else {
        control.value = "";
      }
    });
    root.querySelectorAll("select").forEach(function (select) {
      select.selectedIndex = 0;
    });
    status.textContent = "";
    Object.values(views).forEach(function (view) {
      view.list.replaceChildren();
      view.empty.hidden = false;
    });
  }

  addNoteButton.addEventListener("click", addNote);
  addClaimButton.addEventListener("click", addClaim);
  addEventButton.addEventListener("click", addEvent);
  addEvidenceButton.addEventListener("click", addEvidence);
  addCorroboratorButton.addEventListener("click", addCorroborator);
  addConnectionButton.addEventListener("click", addConnection);
  discardLink.addEventListener("click", clearWorkspace);
  window.addEventListener("pagehide", clearWorkspace);
  window.addEventListener("pageshow", function () {
    if (!workspace) {
      workspace = createWorkspace();
      nextLocalId = 1;
      renderWorkspace();
    }
  });

  renderWorkspace();
})();
