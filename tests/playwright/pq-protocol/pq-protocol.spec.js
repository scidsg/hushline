import { expect, test } from "@playwright/test";

test("PQXDH and repeated SPQR epochs stay bound to authenticated context", async ({
  page,
}) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const aliceClient = window.HushLinePqProtocol.createWorkerClient();
    const bobClient = window.HushLinePqProtocol.createWorkerClient();
    const aliceAccount = "11111111-1111-4111-8111-111111111111";
    const aliceDevice = "22222222-2222-4222-8222-222222222222";
    const bobAccount = "33333333-3333-4333-8333-333333333333";
    const bobDevice = "44444444-4444-4444-8444-444444444444";
    const conversationId = "55555555-5555-4555-8555-555555555555";
    const aliceAddress = {
      name: `${aliceAccount}.${aliceDevice}`,
      deviceId: 1,
    };
    const bobAddress = { name: `${bobAccount}.${bobDevice}`, deviceId: 1 };
    const alice = await aliceClient.createDevice({
      address: aliceAddress,
      prekeyCount: 4,
      prekeyStart: 1,
      signedPrekeyId: 101,
    });
    const bob = await bobClient.createDevice({
      address: bobAddress,
      prekeyCount: 4,
      prekeyStart: 1001,
      signedPrekeyId: 1101,
    });
    const remoteBundle = (device, index, membershipSequence) => {
      const selected = device.publicBundle.prekeys[index];
      return {
        address: device.publicBundle.address,
        identityKey: device.publicBundle.identityKey,
        kyberPrekey: selected.kyberPrekey,
        membershipSequence,
        prekey: { id: selected.id, publicKey: selected.publicKey },
        protocol: device.publicBundle.protocol,
        registrationId: device.publicBundle.registrationId,
        signedPrekey: device.publicBundle.signedPrekey,
        suite: device.publicBundle.suite,
      };
    };
    let aliceState = (
      await aliceClient.beginSession({
        remoteBundle: remoteBundle(bob, 0, 1),
        state: alice.state,
      })
    ).state;
    let bobState = bob.state;
    let bobMembershipSequence = 1;
    let counter = 0;
    const observations = [];
    const context = (senderIsAlice, sequence) => ({
      account_recipient_id: senderIsAlice ? bobAccount : aliceAccount,
      archive_epoch: 0,
      capability_offer: ["HL-PQCHAT-1"],
      capability_selection: "HL-PQCHAT-1",
      conversation_id: conversationId,
      device_recipient_id: senderIsAlice ? bobDevice : aliceDevice,
      key_version: senderIsAlice ? 1101 : 101,
      message_id: `66666666-6666-4666-8666-${String(sequence).padStart(
        12,
        "0",
      )}`,
      protocol: "HL-PQCHAT-1",
      purpose: "transport",
      recipient_membership_sequence: senderIsAlice ? bobMembershipSequence : 1,
      sender_account_id: senderIsAlice ? aliceAccount : bobAccount,
      sender_device_id: senderIsAlice ? aliceDevice : bobDevice,
      sender_membership_sequence: senderIsAlice ? 1 : bobMembershipSequence,
      suite: "SIGNAL-PQXDH3-KYBER1024-SPQR1",
    });
    const exchange = async (senderIsAlice) => {
      const sequence = ++counter;
      const messageContext = context(senderIsAlice, sequence);
      const sender = senderIsAlice ? aliceClient : bobClient;
      const recipient = senderIsAlice ? bobClient : aliceClient;
      const encrypted = await sender.ratchetEncrypt({
        context: messageContext,
        plaintext: `synthetic-${sequence}`,
        state: senderIsAlice ? aliceState : bobState,
      });
      if (senderIsAlice) aliceState = encrypted.state;
      else bobState = encrypted.state;
      if (encrypted.observation) observations.push(encrypted.observation);
      const decrypted = await recipient.ratchetDecrypt({
        ciphertext: encrypted.ciphertext,
        context: messageContext,
        senderAddress: senderIsAlice ? aliceAddress : bobAddress,
        state: senderIsAlice ? bobState : aliceState,
      });
      if (senderIsAlice) bobState = decrypted.state;
      else aliceState = decrypted.state;
      if (decrypted.observation) observations.push(decrypted.observation);
      if (decrypted.plaintext !== `synthetic-${sequence}`) {
        throw new Error("plaintext mismatch");
      }
      return { encrypted, decrypted };
    };

    const handshake = await exchange(true);
    const response = await exchange(false);
    let attempts = 0;
    while (new Set(observations.map((item) => item.epoch)).size < 2) {
      if (attempts++ >= 2048) throw new Error("SPQR epoch bound exceeded");
      await exchange(true);
      await exchange(false);
    }

    let replacementRejected = false;
    try {
      await aliceClient.beginSession({
        remoteBundle: remoteBundle(bob, 1, 1),
        state: aliceState,
      });
    } catch (error) {
      replacementRejected = error.code === "STATE_CONFLICT";
    }

    const reorderedBase = bobState;
    const firstReorderedContext = context(true, ++counter);
    const firstReordered = await aliceClient.ratchetEncrypt({
      context: firstReorderedContext,
      plaintext: "reordered-first",
      state: aliceState,
    });
    aliceState = firstReordered.state;
    const secondReorderedContext = context(true, ++counter);
    const secondReordered = await aliceClient.ratchetEncrypt({
      context: secondReorderedContext,
      plaintext: "reordered-second",
      state: aliceState,
    });
    aliceState = secondReordered.state;
    const secondReceived = await bobClient.ratchetDecrypt({
      ciphertext: secondReordered.ciphertext,
      context: secondReorderedContext,
      senderAddress: aliceAddress,
      state: reorderedBase,
    });
    const firstReceived = await bobClient.ratchetDecrypt({
      ciphertext: firstReordered.ciphertext,
      context: firstReorderedContext,
      senderAddress: aliceAddress,
      state: secondReceived.state,
    });
    bobState = firstReceived.state;
    const outOfOrderRecovered =
      secondReceived.plaintext === "reordered-second" &&
      firstReceived.plaintext === "reordered-first";

    const beforeTamper = bobState;
    const tamperContext = context(true, ++counter);
    const tamperCiphertext = await aliceClient.ratchetEncrypt({
      context: tamperContext,
      plaintext: "context-bound",
      state: aliceState,
    });
    aliceState = tamperCiphertext.state;
    let substitutedContextRejected = false;
    try {
      await bobClient.ratchetDecrypt({
        ciphertext: tamperCiphertext.ciphertext,
        context: {
          ...tamperContext,
          conversation_id: "77777777-7777-4777-8777-777777777777",
        },
        senderAddress: aliceAddress,
        state: beforeTamper,
      });
    } catch (error) {
      substitutedContextRejected = error.code === "AUTHENTICATION_FAILED";
    }
    const accepted = await bobClient.ratchetDecrypt({
      ciphertext: tamperCiphertext.ciphertext,
      context: tamperContext,
      senderAddress: aliceAddress,
      state: beforeTamper,
    });
    bobState = accepted.state;
    let substitutedParticipantRejected = false;
    try {
      await bobClient.ratchetDecrypt({
        ciphertext: tamperCiphertext.ciphertext,
        context: {
          ...tamperContext,
          sender_device_id: "88888888-8888-4888-8888-888888888888",
        },
        senderAddress: aliceAddress,
        state: beforeTamper,
      });
    } catch (error) {
      substitutedParticipantRejected = error.code === "AUTHENTICATION_FAILED";
    }
    const mutate = (value) => {
      const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
      const bytes = Uint8Array.from(
        atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "=")),
        (character) => character.charCodeAt(0),
      );
      bytes[bytes.length - 1] ^= 1;
      return btoa(String.fromCharCode(...bytes))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/u, "");
    };
    let ciphertextRejected = false;
    try {
      await bobClient.ratchetDecrypt({
        ciphertext: mutate(tamperCiphertext.ciphertext),
        context: tamperContext,
        senderAddress: aliceAddress,
        state: beforeTamper,
      });
    } catch (error) {
      ciphertextRejected = error.code === "AUTHENTICATION_FAILED";
    }
    let replayRejected = false;
    try {
      await bobClient.ratchetDecrypt({
        ciphertext: tamperCiphertext.ciphertext,
        context: tamperContext,
        senderAddress: aliceAddress,
        state: bobState,
      });
    } catch (error) {
      replayRejected = ["AUTHENTICATION_FAILED", "PREKEY_REPLAY"].includes(
        error.code,
      );
    }
    let staleReplacementRejected = false;
    try {
      await aliceClient.beginSession({
        remoteBundle: remoteBundle(bob, 1, 1),
        replaceExisting: true,
        state: aliceState,
      });
    } catch (error) {
      staleReplacementRejected = error.code === "STALE_MEMBERSHIP";
    }
    bobMembershipSequence = 2;
    const replacement = await aliceClient.beginSession({
      remoteBundle: remoteBundle(bob, 1, bobMembershipSequence),
      replaceExisting: true,
      state: aliceState,
    });
    aliceState = replacement.state;
    const replacementContext = context(true, ++counter);
    const replacementCiphertext = await aliceClient.ratchetEncrypt({
      context: replacementContext,
      plaintext: "authenticated replacement",
      state: aliceState,
    });
    aliceState = replacementCiphertext.state;
    const replacementPlaintext = await bobClient.ratchetDecrypt({
      ciphertext: replacementCiphertext.ciphertext,
      context: replacementContext,
      senderAddress: aliceAddress,
      state: bobState,
    });
    const replacementSucceeded =
      replacementPlaintext.plaintext === "authenticated replacement" &&
      replacementPlaintext.status.handshakeComplete;
    aliceClient.close();
    bobClient.close();
    return {
      ciphertextRejected,
      handshakeContinuous: handshake.decrypted.status.continuousPq,
      handshakeType: handshake.encrypted.messageType,
      responseType: response.encrypted.messageType,
      observedEpochs: [...new Set(observations.map((item) => item.epoch))],
      outOfOrderRecovered,
      replacementRejected,
      replacementPendingCompliant: replacement.status.continuousPq,
      replacementSucceeded,
      replayRejected,
      staleReplacementRejected,
      status: accepted.status,
      substitutedContextRejected,
      substitutedParticipantRejected,
    };
  });

  expect(result.handshakeType).not.toBe(result.responseType);
  expect(result.handshakeContinuous).toBe(false);
  expect(result.observedEpochs.length).toBeGreaterThanOrEqual(2);
  expect(result.outOfOrderRecovered).toBe(true);
  expect(result.ciphertextRejected).toBe(true);
  expect(result.replacementRejected).toBe(true);
  expect(result.replacementPendingCompliant).toBe(false);
  expect(result.replacementSucceeded).toBe(true);
  expect(result.staleReplacementRejected).toBe(true);
  expect(result.substitutedContextRejected).toBe(true);
  expect(result.substitutedParticipantRejected).toBe(true);
  expect(result.replayRejected).toBe(true);
  expect(result.status.handshakeComplete).toBe(true);
  expect(result.status.continuousPq).toBe(true);
});

test("invalid classical or PQ contribution fails without fallback", async ({
  page,
}) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const localClient = window.HushLinePqProtocol.createWorkerClient();
    const remoteClient = window.HushLinePqProtocol.createWorkerClient();
    const createLocal = () =>
      localClient.createDevice({
        address: { name: crypto.randomUUID(), deviceId: 1 },
        prekeyCount: 2,
        prekeyStart: 1,
        signedPrekeyId: 101,
      });
    const remote = await remoteClient.createDevice({
      address: { name: "remote-device", deviceId: 1 },
      prekeyCount: 2,
      prekeyStart: 1001,
      signedPrekeyId: 1101,
    });
    const mutate = (value) => {
      const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
      const bytes = Uint8Array.from(
        atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "=")),
        (character) => character.charCodeAt(0),
      );
      bytes[bytes.length - 1] ^= 1;
      return btoa(String.fromCharCode(...bytes))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/u, "");
    };
    const attempt = async (field) => {
      const local = await createLocal();
      const selected = remote.publicBundle.prekeys[0];
      const bundle = structuredClone({
        address: remote.publicBundle.address,
        identityKey: remote.publicBundle.identityKey,
        kyberPrekey: selected.kyberPrekey,
        membershipSequence: 1,
        prekey: { id: selected.id, publicKey: selected.publicKey },
        protocol: remote.publicBundle.protocol,
        registrationId: remote.publicBundle.registrationId,
        signedPrekey: remote.publicBundle.signedPrekey,
        suite: remote.publicBundle.suite,
      });
      if (field === "classical") {
        bundle.signedPrekey.signature = mutate(bundle.signedPrekey.signature);
      } else {
        bundle.kyberPrekey.signature = mutate(bundle.kyberPrekey.signature);
      }
      try {
        await localClient.beginSession({
          remoteBundle: bundle,
          state: local.state,
        });
        return false;
      } catch (error) {
        return Boolean(error.code);
      }
    };
    const classicalRejected = await attempt("classical");
    const pqRejected = await attempt("pq");
    localClient.close();
    remoteClient.close();
    return { classicalRejected, pqRejected };
  });

  expect(result).toEqual({ classicalRejected: true, pqRejected: true });
});

test("hybrid archive copies unlock in a fresh browser and reject substitution", async ({
  page,
}) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const creator = window.HushLinePqProtocol.createWorkerClient();
    const freshBrowser = window.HushLinePqProtocol.createWorkerClient();
    const senderAccount = "33333333-3333-4333-8333-333333333333";
    const recipientAccount = "55555555-5555-4555-8555-555555555555";
    const senderRootBytes = crypto.getRandomValues(new Uint8Array(32));
    const recipientRootBytes = crypto.getRandomValues(new Uint8Array(32));
    const encode = (bytes) =>
      btoa(String.fromCharCode(...bytes))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/u, "");
    const decode = (value) => {
      const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
      return Uint8Array.from(
        atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "=")),
        (character) => character.charCodeAt(0),
      );
    };
    const mutate = (value) => {
      const bytes = decode(value);
      bytes[bytes.length - 1] ^= 1;
      return encode(bytes);
    };
    const senderRoot = encode(senderRootBytes);
    const recipientRoot = encode(recipientRootBytes);
    senderRootBytes.fill(0);
    recipientRootBytes.fill(0);
    const senderEpoch = await creator.createArchiveEpoch({
      accountId: senderAccount,
      accountRoot: senderRoot,
      epoch: 7,
    });
    const recipientEpoch = await creator.createArchiveEpoch({
      accountId: recipientAccount,
      accountRoot: recipientRoot,
      epoch: 11,
    });
    const baseContext = {
      capability_offer: ["HL-PQCHAT-1"],
      capability_selection: "HL-PQCHAT-1",
      conversation_id: "22222222-2222-4222-8222-222222222222",
      device_recipient_id: "00000000-0000-0000-0000-000000000000",
      message_id: "11111111-1111-4111-8111-111111111111",
      protocol: "HL-PQCHAT-1",
      purpose: "archive",
      sender_account_id: senderAccount,
      sender_device_id: "44444444-4444-4444-8444-444444444444",
      sender_membership_sequence: 12,
      suite: "MLKEM768-X25519-HKDF-SHA256-AES256GCM",
    };
    const senderContext = {
      ...baseContext,
      account_recipient_id: senderAccount,
      archive_epoch: 7,
      key_version: 7,
      recipient_membership_sequence: 12,
    };
    const recipientContext = {
      ...baseContext,
      account_recipient_id: recipientAccount,
      archive_epoch: 11,
      key_version: 11,
      recipient_membership_sequence: 18,
    };
    const plaintext = "offline unread synthetic disclosure";
    const senderCiphertext = await creator.archiveSeal({
      context: senderContext,
      plaintext,
      publicKey: senderEpoch.publicKey,
    });
    const recipientCiphertext = await creator.archiveSeal({
      context: recipientContext,
      plaintext,
      publicKey: recipientEpoch.publicKey,
    });
    const open = (accountId, accountRoot, epoch, context, ciphertext) =>
      freshBrowser.archiveOpen({
        accountId,
        accountRoot,
        ciphertext,
        context,
        encryptedPrivateKey: epoch.encryptedPrivateKey,
        epoch: epoch.epoch,
        publicKey: epoch.publicKey,
      });
    const rejected = async (operation) => {
      try {
        await operation();
        return false;
      } catch (error) {
        return error.code === "AUTHENTICATION_FAILED";
      }
    };
    const senderPlaintext = await open(
      senderAccount,
      senderRoot,
      senderEpoch,
      senderContext,
      senderCiphertext,
    );
    const recipientPlaintext = await open(
      recipientAccount,
      recipientRoot,
      recipientEpoch,
      recipientContext,
      recipientCiphertext,
    );
    const wrongPasswordRejected = await rejected(() =>
      open(
        senderAccount,
        encode(crypto.getRandomValues(new Uint8Array(32))),
        senderEpoch,
        senderContext,
        senderCiphertext,
      ),
    );
    const ciphertextRejected = await rejected(() =>
      open(
        senderAccount,
        senderRoot,
        senderEpoch,
        senderContext,
        mutate(senderCiphertext),
      ),
    );
    const contextRejected = await rejected(() =>
      open(
        senderAccount,
        senderRoot,
        senderEpoch,
        {
          ...senderContext,
          conversation_id: "99999999-9999-4999-8999-999999999999",
        },
        senderCiphertext,
      ),
    );
    const keySubstitutionRejected = await rejected(() =>
      freshBrowser.archiveOpen({
        accountId: senderAccount,
        accountRoot: senderRoot,
        ciphertext: senderCiphertext,
        context: senderContext,
        encryptedPrivateKey: recipientEpoch.encryptedPrivateKey,
        epoch: senderEpoch.epoch,
        publicKey: recipientEpoch.publicKey,
      }),
    );
    const nextEpoch = await creator.createArchiveEpoch({
      accountId: senderAccount,
      accountRoot: senderRoot,
      epoch: 8,
    });
    const nextContext = {
      ...senderContext,
      archive_epoch: 8,
      key_version: 8,
      message_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    };
    const nextCiphertext = await creator.archiveSeal({
      context: nextContext,
      plaintext: "new epoch disclosure",
      publicKey: nextEpoch.publicKey,
    });
    const oldAfterRotation = await open(
      senderAccount,
      senderRoot,
      senderEpoch,
      senderContext,
      senderCiphertext,
    );
    const newAfterRotation = await open(
      senderAccount,
      senderRoot,
      nextEpoch,
      nextContext,
      nextCiphertext,
    );
    creator.close();
    freshBrowser.close();
    return {
      ciphertextRejected,
      contextRejected,
      independentCopies: senderCiphertext !== recipientCiphertext,
      keySubstitutionRejected,
      newAfterRotation,
      noProtocolSecrets: [senderEpoch, recipientEpoch, nextEpoch].every(
        (epoch) =>
          !JSON.stringify(epoch).match(/identity|prekey|ratchet|session/iu),
      ),
      oldAfterRotation,
      recipientPlaintext,
      senderCiphertextBytes: decode(senderCiphertext).length,
      senderPlaintext,
      wrongPasswordRejected,
    };
  });

  expect(result).toEqual({
    ciphertextRejected: true,
    contextRejected: true,
    independentCopies: true,
    keySubstitutionRejected: true,
    newAfterRotation: "new epoch disclosure",
    noProtocolSecrets: true,
    oldAfterRotation: "offline unread synthetic disclosure",
    recipientPlaintext: "offline unread synthetic disclosure",
    senderCiphertextBytes: 1171,
    senderPlaintext: "offline unread synthetic disclosure",
    wrongPasswordRejected: true,
  });
});

test("protocol state advances only with the encrypted browser transaction", async ({
  page,
}) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const client = window.HushLinePqProtocol.createWorkerClient();
    const peer = window.HushLinePqProtocol.createWorkerClient();
    const localAccount = "11111111-1111-4111-8111-111111111111";
    const localDevice = "22222222-2222-4222-8222-222222222222";
    const peerAccount = "33333333-3333-4333-8333-333333333333";
    const peerDevice = "44444444-4444-4444-8444-444444444444";
    const conversationId = "55555555-5555-4555-8555-555555555555";
    const messageId = "66666666-6666-4666-8666-666666666666";
    const localAddress = {
      name: `${localAccount}.${localDevice}`,
      deviceId: 1,
    };
    const peerAddress = {
      name: `${peerAccount}.${peerDevice}`,
      deviceId: 1,
    };
    const local = await client.createDevice({
      address: localAddress,
      prekeyCount: 2,
      prekeyStart: 1,
      signedPrekeyId: 101,
    });
    const remote = await peer.createDevice({
      address: peerAddress,
      prekeyCount: 2,
      prekeyStart: 1001,
      signedPrekeyId: 1101,
    });
    const established = await client.beginSession({
      remoteBundle: {
        address: remote.publicBundle.address,
        identityKey: remote.publicBundle.identityKey,
        kyberPrekey: remote.publicBundle.prekeys[0].kyberPrekey,
        membershipSequence: 1,
        prekey: {
          id: remote.publicBundle.prekeys[0].id,
          publicKey: remote.publicBundle.prekeys[0].publicKey,
        },
        protocol: remote.publicBundle.protocol,
        registrationId: remote.publicBundle.registrationId,
        signedPrekey: remote.publicBundle.signedPrekey,
        suite: remote.publicBundle.suite,
      },
      state: local.state,
    });
    const storageKey = await window.HushLinePqBrowserState.importStorageKey(
      crypto.getRandomValues(new Uint8Array(32)),
    );
    const session = await window.HushLinePqProtocol.createPersistedSession({
      accountId: localAccount,
      client,
      deviceId: localDevice,
      initialState: established.state,
      leaseOwnerId: "protocol-test",
      sessionBinding: "authenticated-session",
      sessionId: `${conversationId}:${peerDevice}`,
      storageKey,
    });
    const context = {
      account_recipient_id: peerAccount,
      archive_epoch: 0,
      capability_offer: ["HL-PQCHAT-1"],
      capability_selection: "HL-PQCHAT-1",
      conversation_id: conversationId,
      device_recipient_id: peerDevice,
      key_version: 1101,
      message_id: messageId,
      protocol: "HL-PQCHAT-1",
      purpose: "transport",
      recipient_membership_sequence: 1,
      sender_account_id: localAccount,
      sender_device_id: localDevice,
      sender_membership_sequence: 1,
      suite: "SIGNAL-PQXDH3-KYBER1024-SPQR1",
    };
    await session.encrypt({
      buildRequest: ({ ciphertext }) => ({ ciphertext, context }),
      context,
      idempotencyKey: "a".repeat(64),
      logicalMessageId: messageId,
      plaintext: "transactional synthetic message",
    });
    const pending = await session.listOutbox();
    await session.deliverOutbox(messageId, async (request) => ({
      conversation_version: 1,
      idempotent: false,
      message_id: JSON.parse(new TextDecoder().decode(request)).context
        .message_id,
    }));
    const remaining = await session.listOutbox();
    await session.close();
    peer.close();
    return {
      pending: pending.length,
      pendingMessageId: pending[0]?.logicalMessageId,
      remaining: remaining.length,
    };
  });

  expect(result).toEqual({
    pending: 1,
    pendingMessageId: "66666666-6666-4666-8666-666666666666",
    remaining: 0,
  });
});
