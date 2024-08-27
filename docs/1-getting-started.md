# Getting Started as a Hush Line Operator

Hush Line is a free and open-source, whistleblowing platform for organizations or individuals. It's intended for journalists and newsrooms to offer a public tip line, by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

We strongly encourage all Hush Line operators to add a PGP key to ensure messages are encrypted, only readable by the key owner if the database is compromised. 

## Contents

[Option 1: Proton _(Recommended)_](#option-1-proton)<br>
[Option 2: Mailvelope](#option-2-mailvelope)

### Option 1: Proton

#### Step 1: Sign up for Hush Line & Proton 

Go to hushline.app and proton.me and sign up for your accounts if you haven't already.

![step1](https://github.com/user-attachments/assets/ae83a9a5-9dfb-47cb-9b78-9868aee0c2b2)

#### Step 2: Import Your Key

In your Hush Line settings, navigate to the Email & Encryption tab. You'll notice that email forwarding is disabled until you add an encryption key.

In the `Message Encryption` section, you'll see a Proton key search input. To import your key, add the email address you just created. 

![step2](https://github.com/user-attachments/assets/74df8729-1aea-4925-871b-fd829af3e79f)

#### Step 3: Mail Forwarding

Now that you've added your PGP key from Proton you can add a forwarding address. Add your Proton email address.

![step3](https://github.com/user-attachments/assets/32f2f7be-0414-4da4-97cf-2629790ff690)

#### Step 4: Send a Message

Click on `Profile` in the Hush Line global navigation. Enter a message into your form, and when you submit it, you'll see it encrypted in your browser before it sends - this ensures your message is end-to-end encrypted!

![step4](https://github.com/user-attachments/assets/b4af8be5-fd9f-4a36-a7c3-3817e6bf6f56)

#### Step 5: Check Your Email

Go back to your Proton account and, if necessary, refresh your Inbox. You should see an email from `notifications@hushline.app` appear. Click on it, and you'll see your automatically decrypted message! If you go back to Hush Line and click `Inbox`, you'll see the same message, but it'll be encrypted and unreadable since your key to decrypt the message only exists on Proton.

![step5](https://github.com/user-attachments/assets/0b1dfb8e-21a2-42a7-9018-c63c5fdf3c69)

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

![step2 2](https://github.com/user-attachments/assets/f151eeb2-c567-4733-b90a-2fded08f9a55)

#### Step 3: Add your key to Hush Line

Select the `Email & Encryption` tab in your Hush Line settings, and paste your key into the Public PGP Key textarea.

![step2 3](https://github.com/user-attachments/assets/6f4b6c60-a331-4405-a094-46596bea330b)

#### Step 4: Authorize the Hush Line domain

With Hush Line open, click the Mailvelope icon and select "Authorize this domain." Click "Ok" when the dialog opens. You'll be able to see `tips.hushline.app` in the authorized domains list. 

![step2 4](https://github.com/user-attachments/assets/dd5dadbb-5afe-4ac3-a4f2-126f289ce6dc)

#### Step 5: Send and read a message!

Let's send a test message! In the header, click "Profile." Enter some text and click "Send Message." If you haven't disabled JavaScript, you'll see it encrypted in the browser before it submits. Go to "Inbox" to see the message in the app. You may have to enter the password you set when creating your key in Mailvelope.

![step1 3](https://github.com/user-attachments/assets/1cd81ba0-4c54-49e4-8352-2008436984fd)


🎉 Congratulations, you're ready to start receiving encrypted and anonymous Hush Line messages!
