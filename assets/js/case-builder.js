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
  const reviewKind = document.getElementById("case-review-kind");
  const reviewDescription = document.getElementById("case-review-description");
  const reviewUncertain = document.getElementById("case-review-uncertain");
  const reviewIdentifying = document.getElementById("case-review-identifying");
  const addReviewButton = document.getElementById("case-review-add");
  const continueButton = document.getElementById("case-review-continue");
  const stopButton = document.getElementById("case-review-stop");
  const decision = document.getElementById("case-review-decision");

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
    gapsAndRisks: {
      empty: document.getElementById("case-review-empty"),
      list: document.getElementById("case-review-list"),
    },
  };

  const collectionNames = {
    claim: "claims",
    event: "timelineEvents",
    evidence: "evidenceItems",
    corroborator: "corroborators",
    connection: "relationships",
    review: "gapsAndRisks",
  };

  const itemTypeLabels = {
    claim: "Claim",
    event: "Event",
    evidence: "Evidence",
    corroborator: "Corroborator",
    review: "Review reminder",
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

  function reviewMarkers(record, additionalMarkers = []) {
    return [
      ...additionalMarkers,
      record.review.uncertainty === "uncertain" ? "Uncertain" : "",
      record.review.sensitivity === "sensitive" ? "Sensitive or identifying" : "",
      record.disposition === "set_aside" ? "Set aside" : "",
    ];
  }

  function focusRecordAction(recordId, label) {
    const card = Array.from(document.querySelectorAll("[data-record-id]")).find(function (
      candidate,
    ) {
      return candidate.dataset.recordId === recordId;
    });
    if (!card) return;
    const button = Array.from(card.querySelectorAll("button")).find(function (candidate) {
      return candidate.textContent === label;
    });
    if (button) button.focus();
  }

  function addReviewActions(card, record) {
    const actions = document.createElement("div");
    actions.className = "case-record-actions case-review-actions";
    const uncertaintyLabel =
      record.review.uncertainty === "uncertain" ? "Clear uncertainty" : "Mark uncertain";
    const sensitivityLabel =
      record.review.sensitivity === "sensitive"
        ? "Clear sensitive marker"
        : "Mark sensitive or identifying";
    const dispositionLabel =
      record.disposition === "set_aside" ? "Return to preparation" : "Set aside";

    actions.append(
      createButton(uncertaintyLabel, "btn", function () {
        record.review.uncertainty =
          record.review.uncertainty === "uncertain" ? "unmarked" : "uncertain";
        updateAudit(record.audit);
        updateAudit(workspace.audit);
        renderWorkspace();
        const nextLabel =
          record.review.uncertainty === "uncertain" ? "Clear uncertainty" : "Mark uncertain";
        announce("Uncertainty marker updated.");
        focusRecordAction(record.id, nextLabel);
      }),
      createButton(sensitivityLabel, "btn", function () {
        record.review.sensitivity =
          record.review.sensitivity === "sensitive" ? "unmarked" : "sensitive";
        updateAudit(record.audit);
        updateAudit(workspace.audit);
        renderWorkspace();
        const nextLabel =
          record.review.sensitivity === "sensitive"
            ? "Clear sensitive marker"
            : "Mark sensitive or identifying";
        announce("Sensitivity marker updated.");
        focusRecordAction(record.id, nextLabel);
      }),
      createButton(dispositionLabel, "btn", function () {
        record.disposition = record.disposition === "set_aside" ? "active" : "set_aside";
        updateAudit(record.audit);
        updateAudit(workspace.audit);
        renderWorkspace();
        const nextLabel =
          record.disposition === "set_aside" ? "Return to preparation" : "Set aside";
        announce(
          record.disposition === "set_aside"
            ? "Item set aside in the open page."
            : "Item returned to preparation.",
        );
        focusRecordAction(record.id, nextLabel);
      }),
    );
    card.appendChild(actions);
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
      item.dataset.recordId = note.id;
      addText(item, "case-note-text", note.text);
      addMarkers(item, reviewMarkers(note));
      addReviewActions(item, note);

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
      addMarkers(item, reviewMarkers(claim));
      addReviewActions(item, claim);
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
      addMarkers(item, reviewMarkers(event, [event.approximate ? "Approximate date" : ""]));
      addReviewActions(item, event);
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
      addMarkers(
        item,
        reviewMarkers(evidence, [
          evidence.availability === "missing" ? "Missing or unavailable" : "Available",
          evidence.review.accessRisk === "risky" ? "Risky to access — leave it alone" : "",
        ]),
      );
      addReviewActions(item, evidence);
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
      addMarkers(item, reviewMarkers(corroborator));
      addReviewActions(item, corroborator);
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

  function renderGapsAndRisks() {
    const view = views.gapsAndRisks;
    view.list.replaceChildren();
    view.empty.hidden = workspace.gapsAndRisks.length !== 0;
    workspace.gapsAndRisks.forEach(function (reviewItem) {
      const item = document.createElement("li");
      item.className = "case-record-card case-review-card";
      item.dataset.recordId = reviewItem.id;
      const title = document.createElement("h4");
      title.textContent = reviewItem.kind === "gap" ? "Incomplete area" : "Possible consequence";
      item.appendChild(title);
      addText(item, "case-record-text", reviewItem.description);
      addMarkers(item, reviewMarkers(reviewItem));
      addReviewActions(item, reviewItem);
      addDeleteAction(item, reviewItem, "review", addReviewButton);
      view.list.appendChild(item);
    });
  }

  function renderDecision() {
    const nextAction = workspace.sharePlan.nextAction;
    decision.hidden = !nextAction;
    if (nextAction === "continue") {
      decision.textContent =
        "You chose to continue preparing. Nothing has been shared, saved, or submitted.";
    } else if (nextAction === "pause_in_open_page") {
      decision.textContent =
        "You chose not to proceed right now. Nothing has been shared. " +
        "This page does not save your work; close it or use Discard & leave if you do not want " +
        "to keep it visible.";
    } else {
      decision.textContent = "";
    }
  }

  function renderWorkspace() {
    renderNotes();
    renderClaims();
    renderTimeline();
    renderEvidence();
    renderCorroborators();
    renderRelationships();
    renderGapsAndRisks();
    renderConnectionOptions();
    renderDecision();
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
      review: {
        uncertainty: claimUncertain.checked ? "uncertain" : "unmarked",
        sensitivity: "unmarked",
      },
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
      review: {
        uncertainty: eventApproximate.checked ? "uncertain" : "unmarked",
        sensitivity: "unmarked",
      },
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
        sensitivity: "unmarked",
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
      review: {
        uncertainty: corroboratorUncertain.checked ? "uncertain" : "unmarked",
        sensitivity: "unmarked",
      },
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

  function addReviewReminder() {
    const description = reviewDescription.value.trim();
    if (!description) {
      announce("Enter a short reminder before adding it.");
      reviewDescription.focus();
      return;
    }
    workspace.gapsAndRisks.push({
      id: nextId("review"),
      audit: createAudit(),
      review: {
        uncertainty: reviewUncertain.checked ? "uncertain" : "unmarked",
        sensitivity: reviewIdentifying.checked ? "sensitive" : "unmarked",
      },
      disposition: "active",
      kind: reviewKind.value,
      description,
    });
    updateAudit(workspace.audit);
    reviewKind.value = "gap";
    reviewDescription.value = "";
    reviewUncertain.checked = false;
    reviewIdentifying.checked = false;
    renderWorkspace();
    announce("Review reminder added to the open page.");
    reviewDescription.focus();
  }

  function chooseNextAction(nextAction) {
    workspace.sharePlan.nextAction = nextAction;
    updateAudit(workspace.sharePlan.audit);
    updateAudit(workspace.audit);
    renderDecision();
    if (nextAction === "continue") {
      announce("Continue preparing selected. Nothing was shared.");
    } else {
      announce("Do not proceed right now selected. Nothing was shared.");
    }
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
    decision.textContent = "";
    decision.hidden = true;
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
  addReviewButton.addEventListener("click", addReviewReminder);
  continueButton.addEventListener("click", function () {
    chooseNextAction("continue");
  });
  stopButton.addEventListener("click", function () {
    chooseNextAction("pause_in_open_page");
  });
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
