# Getting Started as a Hush Line Operator

Hush Line is a free and open-source, whistleblowing platform for organizations or individuals. It's intended for journalists and newsrooms to offer a public tip line, by educators and school administrators to provide students with a safe way to report potentially sensitive information, or employers, Board rooms, and C-suites for anonymous employee reporting.

## Contents

1. Email Encryption
   - [Option 1: Proton _(Recommended)_](#option-1-proton)
   - [Option 2: Mailvelope and Gmail](#option-2-mailvelope--gmail)
2. [Message Forwarding](#message-forwarding)

## Email Encryption

We strongly encourage all Hush Line operators to add a PGP key to ensure messages are encrypted, only readable by the key owner if the database is compromised. 

We'll use Mailvelope, an open-source, cross-browser extension that allows you to decrypt messages directly in the app.

### Option 1: Proton

#### Step 1: Sign up for Proton

Go to proton.me and sign up for an account if you don't have one already.

#### Step 2: Import Your Key

In your Hush Line settings, navigate to the `Email & Encryption` tab. You'll notice that email forwarding is disabled until you add an encryption key. 

In the `Message Encryption` section you'll see a Proton key search input. Add the email address you just created to import your key.

#### Step 3: Mail Forwarding

Now that you've added your PGP key from Proton you can add a forwarding address. Add your Proton email address.

#### Step 4: Send a Message

Click on `Submit Message` in the Hush Line global navigation. Enter a message into your form and when you submit it you'll see it encrypt in your browser before it sends - this ensures your message is end-to-end encrypted!

#### Step 5: Check Your Email!

Go back to your Proton account and if necessary refresh your inbox. You should see an email from `notifications@hushline.app` appear. Click on it, and you'll see your automatically decrypted message! If you go back to Hush Line and click `Inbox` you'll see the same message, but it'll be encrypted and unreadable since your key to decrypt the message only exists on Proton.

### Option 2: Mailvelope & Gmail

#### Step 1: Get the extension

Mailvelope is available in Firefox and Chrome and we'll use Firefox as our example. First, click on the menu icon with three horizontal lines in the top right of your browser. Then select "Add-ons and themes".

![step1](https://github.com/user-attachments/assets/b8a64098-9c89-4c64-a7bc-bda3bf6e884f)

#### Step 2: Search for Mailvelope

In the search bar at the top of the screen, enter `Mailvelope` and select the correct result.

![step2](https://github.com/user-attachments/assets/615b2516-18f5-4946-8fdb-7dc07272bfe7)

#### Step 3: Create a key

#### Pin the extension

First, we'll pin the extension to our toolbar. Click on the puzzle piece icon, then the settings gear icon for Mailvelope. Select "Pin to Toolbar." When the icon appears, click it, then select "Let's start!".

![step3](https://github.com/user-attachments/assets/ce1eac41-b4ad-4048-b5a2-765fbb5cb36c)

##### Generate your key

In the Setup dashboard, click on the "Generate key" button. Add a name for your key, your email address, and a strong password. Before clicking "Generate," click on the "Advanced" button. In the Algorithm picklist, choose "ECC - Curve25519". This algorithm is more efficient than traditional RSA encryption while providing a similar level of security. Now, generate your key!

![step4](https://github.com/user-attachments/assets/1af3e7f4-041c-4090-80bb-c4c5df4df0c9)

##### Copy the key

Once your key is created, click on it from the dashboard, then select "Export" in the "Public" tab and "Copy to clipboard."

![step5](https://github.com/user-attachments/assets/78a6f52b-9cc2-43e7-9cde-61f87c1e88f4)

### Step 4: Add your key to Hush Line

Select the "Email & Encryption" tab in your Hush Line settings, and paste your key into the Public PGP Key textarea. Now, when you go to your message submission page, you'll see a new encryption indicator at the bottom of the form! 

![step6](https://github.com/user-attachments/assets/59b99f80-0be1-4cfd-a1ec-aa4a3a816d12)

#### Step 5: Authorize the Hush Line domain

With Hush Line open, click the Mailvelope icon and select "Authorize this domain." Click "Ok" when the dialog opens. You'll be able to see `tips.hushline.app` in the authorized domains list. 

![step10](https://github.com/user-attachments/assets/b5fc8852-7b14-4bd0-8b12-ef92eba983ca)

#### Step 6: Send and read a message!

Let's send a test message! In the header, click "Submit Message." Enter some text and click "Send Message." If you haven't disabled JavaScript, you'll see it encrypted in the browser before it submits. Go to "Inbox" to see the message in the app. You may have to enter the password you set when creating your key in Mailvelope.

![step9](https://github.com/user-attachments/assets/04066bc1-8d75-4898-ad9f-0a60efae3ce2)

<br>

--------------

<br>

## Message Forwarding

### SMTP Settings

You'll need SMTP information from your mail provider so Hush Line can email your message. We'll use Gmail because it is highly reliable. If you still need an account, create one. It's a good practice to maintain an email address separate from your personal account.

```
SMTP Username: [your Google email address]
SMTP Server: smtp.gmail.com
SMTP Port: 587
SMTP Password: [app-specific password (see below)]
```

### Step 1: Create an app password

#### Create an app password

You'll need to [enable 2-step authentication for your Google account](https://support.google.com/accounts/answer/185839?hl=en&co=GENIE.Platform%3DDesktop). Then, click "Manage your Google Account" from your Google user menu. In the search bar at the top, enter "app passwords." In the App Passwords screen, enter "Hush Line" in the name, and click "Create." Use this password for your SMTP settings. 

![step7](https://github.com/user-attachments/assets/f08328a6-e12b-4986-a287-996312cbc1f3)

#### Update SMTP information in Hush Line

Now, enter your SMTP information in your Hush Line settings "Email & Encryption" tab.

![step8](https://github.com/user-attachments/assets/218ef288-0380-4e2d-b21d-80e0cff4b0df)

🎉 Congratulations, you're now ready to continue with Hush Line!
