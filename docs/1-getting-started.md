# Getting Started as a Hush Line Operator

Hush Line is a free and open-source, whistleblowing platform for organizations or individuals. It's intended for journalists and newsrooms to offer a public tip line, by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

We strongly encourage all Hush Line operators to add a PGP key to ensure messages are encrypted, only readable by the key owner if the database is compromised. 

## Contents

[Option 1: Proton _(Recommended)_](#option-1-proton)<br>
[Option 2: Mailvelope](#option-2-mailvelope)

### Option 1: Proton

#### Step 1: Sign up for Hush Line & Proton 

Go to hushline.app and proton.me and sign up for your accounts if you haven't already.

![step1](https://github.com/user-attachments/assets/0832d37e-a7d3-4394-9761-3b25a41550e4)

#### Step 2: Import Your Key

In your Hush Line settings, navigate to the Email & Encryption tab. You'll notice that email forwarding is disabled until you add an encryption key.

In the `Message Encryption` section, you'll see a Proton key search input. To import your key, add the email address you just created. 

![step2](https://github.com/user-attachments/assets/acac2953-3689-48c0-9e5b-bb7ded61496b)

#### Step 3: Mail Forwarding

Now that you've added your PGP key from Proton you can add a forwarding address. Add your Proton email address.

![step3](https://github.com/user-attachments/assets/193cddb2-d472-40c1-8c40-79c7733a18e1)

#### Step 4: Send a Message

Click on `Submit Message` in the Hush Line global navigation. Enter a message into your form, and when you submit it, you'll see it encrypted in your browser before it sends - this ensures your message is end-to-end encrypted!

![step4](https://github.com/user-attachments/assets/50c81fb7-b40e-4579-b480-1ebe084975e8)

#### Step 5: Check Your Email

Go back to your Proton account and, if necessary, refresh your Inbox. You should see an email from `notifications@hushline.app` appear. Click on it, and you'll see your automatically decrypted message! If you go back to Hush Line and click `Inbox`, you'll see the same message, but it'll be encrypted and unreadable since your key to decrypt the message only exists on Proton.

![step5](https://github.com/user-attachments/assets/3a7ad652-825f-4f1d-bf3e-8175e8f96e8e)

🎉 Congratulations, you're ready to start receiving encrypted and anonymous Hush Line messages!

<br>

----------

<br>

### Option 2: Mailvelope

#### Step 1: Get the Extension

To set up Mailvelope for Chrome or Firefox, follow the instructions found here: https://mailvelope.com/en/help

#### Step 2: Create a key

In the Setup dashboard, click on the "Generate key" button. Add a name for your key, your email address, and a strong password. Before clicking "Generate," click on the "Advanced" button. In the Algorithm picklist, choose "ECC - Curve25519". This algorithm is more efficient than traditional RSA encryption while providing a similar level of security. Now, generate your key!

Once your key is created, click on it from the dashboard, then select "Export" in the "Public" tab and "Copy to clipboard."

![step1 1](https://github.com/user-attachments/assets/b2156d39-0b8c-43b0-ac52-e34e8ea32fe5)

#### Step 3: Add your key to Hush Line

Select the `Email & Encryption` tab in your Hush Line settings, and paste your key into the Public PGP Key textarea.

![step1 2](https://github.com/user-attachments/assets/07f9731e-00c5-41b4-a661-fb2159e99922)

#### Step 4: Authorize the Hush Line domain

With Hush Line open, click the Mailvelope icon and select "Authorize this domain." Click "Ok" when the dialog opens. You'll be able to see `tips.hushline.app` in the authorized domains list. 

![step1 4](https://github.com/user-attachments/assets/f8c89923-f951-4381-a1fb-dae541c180e5)

#### Step 5: Send and read a message!

Let's send a test message! In the header, click "Submit Message." Enter some text and click "Send Message." If you haven't disabled JavaScript, you'll see it encrypted in the browser before it submits. Go to "Inbox" to see the message in the app. You may have to enter the password you set when creating your key in Mailvelope.

![step1 3](https://github.com/user-attachments/assets/1cd81ba0-4c54-49e4-8352-2008436984fd)


🎉 Congratulations, you're ready to start receiving encrypted and anonymous Hush Line messages!
