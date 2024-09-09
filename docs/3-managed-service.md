# Hush Line Managed Service

The hosted version of Hush Line is the first free and open-source anonymous tip-line-as-a-service and the easiest way to get started. It's as simple as signing up, and you'll have a way for anyone to send you a private message. It's for those needing one or more tip lines without worrying about managing and maintaining technical infrastructure.

## Contents

1. [Register & Log In](#register--login)
2. [Verified Accounts](#verified-accounts)
3. [Sending Messages](#sending-messages)
4. [Reading Messages](#reading-messages)
5. [Settings](#settings)

![Homepage](https://github.com/user-attachments/assets/04ae835e-1caf-4da8-9871-7d274f67d8fc)

## Register & Login

First, register and log in to your account at https://tips.hushline.app/register.

To protect your privacy, we don't require any PII, including your email address or phone number.

![Register](https://github.com/user-attachments/assets/f3846273-e475-42c2-aa86-806a54e32e72)

## Verified Accounts

Our verified accounts feature is designed to ensure that messages reach their intended recipients. Verified accounts are specially available for:

- 🕵️ **Journalists** - Reporters, correspondents, and investigative journalists.
- 📰 **Newsrooms** - Official accounts for newspapers, TV stations, or online news portals.
- ✊ **Activists** - Individuals or groups advocating for social, environmental, or political causes.
- 📸 **Public Figures** - Politicians or other noteworthy public individuals.
- 📊 **Businesses** - Companies, small businesses, or startups aiming to communicate with their audience.

![Profile](https://github.com/user-attachments/assets/b34bb0c8-ad9e-4aef-a412-5085c61bb230)

### Requesting Verification

To ensure your account is recognized as authentic, users belonging to the categories listed above can apply for verification. Follow these steps to initiate the verification process:

1. **First, add a verified URL to your Hush Line profile:** In Hush Line settings you can add up to four additional fields - a URL, Signal username, phone number, or anything else. To verify a URL, you simply need to add a link to your Hush Line address on the page for that URL with `rel="me"` in the link's markup. For example:

   ```html
   <a href="https://tips.hushline.app/to/scidsg" rel="me">Send an anonymous tip!</a>
   ```

   ![verified-url](https://github.com/user-attachments/assets/acd84800-f17e-4e25-a1bf-6315af235ccf)

   a. **Alternatively, verify a Hush Line address using Mastodon:** Add your Mastodon address to your Hush Line profile, then add your Hush Line address to your Mastodon profile. You'll see your Hush Line address verify on Mastodon.

   ![verify-via-mastodon](https://github.com/user-attachments/assets/cd1d25c2-d119-4f9b-9c31-472b0d29ad84)

3. **Set your Display Name:** To help guard against abuse, our verification system is built so that if a verified user changes their username or display name, they'll lose their verified status and need to initiate the process again. This feature is intended to eliminate the risk of a user with a verified account changing their information to impersonate another person or organization.

4. **Send a Message:** Use the contact form in the app to reach out to us to request verification!

## Sending Messages

When you log in to your account, click on the `Profile` link at the top of the screen. You can publicly share the URL for this page wherever you're advertising your tip line. Whistleblowers will use this address to send anonymous messages. To send a message to the Hush Line admin account, someone would visit `https://tips.hushline.app/to/admin`.

![Profile](https://github.com/user-attachments/assets/88ad5abb-001e-4884-908a-5798535e91d5)

## Reading Messages

New users are greeted by their empty inbox.

![Inbox - Empty](https://github.com/user-attachments/assets/a319acfb-59b4-4c37-8746-550156649e1b)

When you receive a message, they'll appear here.

![Inbox - Full](https://github.com/user-attachments/assets/9a1c8216-24d9-4924-be24-4496e3d16fe0)

### Message Encryption

By default, Hush Line requires a PGP key to receive messages, making your messages only readable by you.

## Settings

### Profile Settings

![Settings - Directory](https://github.com/user-attachments/assets/54f18599-0f7f-41b7-ad6a-81166bd6cc6a)

#### Display Name

Users can set a human-readable display name so that someone submitting a message can see "Submit a message to Science & Design" rather than "Submit a message to scidsg". As a security measure, if a user changes their display name after verification, they'll lose that status and must re-verify their account.

#### Public Directory

Users may opt in to being listed on our public directory, making it easy for anyone to find their Hush Line account.

#### Verified Addresses

Verified addresses establishes a relationship between your Hush Line account and another website. Verification is automatic, and all you need to do is include a link to your Hush Line profile containing `rel="me"` on the page of the address you want verified.

For example, if I want to verify my personal website `glennsorrentino.com` I would add this to my page:

```html
<a href="https://tips.hushline.app/to/glenn" rel="me">Hush Line</a>
```

In your Hush Line settings, when I add `https://glennsorrentino.com` you'll see a verified checkmark.

### Authentication

![Settings - Authentication](https://github.com/user-attachments/assets/1b066ce0-d6c9-4224-afcb-d4dece6d8df5)

#### Two-Factor Authentication

To improve account security, users can enable two-factor authentication, making account compromises, even in the event of a password leak, impossible.

#### Change Password

Users can change their password when needed.

#### Change Username

Changing your username is easy but can lead to confusion for end-users, especially for well-known organizations.

##### Verification

Like when changing your display name, when you change your username, you'll lose verification and need to go through the process again.

### Email & Encryption

Before users can enable message forwading, a PGP key must be uploaded.

![Settings - Email](https://github.com/user-attachments/assets/4a1ec530-cf19-432e-81ee-cbbf53da1261)

#### Email Delivery

We use Riseup.net for our email forwarding provider. All you need to do is add an email address and you'll get new secure messages delivered directly to your email inbox.

![Settings - Email](https://github.com/user-attachments/assets/3865afea-ea24-499f-96b0-c6d680e7e3f3)

#### Encryption

![Settings - Encryption](https://github.com/user-attachments/assets/09e63658-7959-4da6-8bd1-c27cedf494ed)

##### Proton

Proton users can easily import their public PGP key by entering their email address. We do not store your email address.

##### PGP Key

A user may manually add their PGP key if not a Proton user.

### Advanced

#### Delete Account

Easily and permanently delete your account whenever you want.

![Settings - Advanced](https://github.com/user-attachments/assets/f65eccac-20bb-42f6-88c6-bd5e4d474231)
