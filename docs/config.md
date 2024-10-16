# Configuration

Hush Line is configured via environment variables.
The following env vars are available to configure the app.

Note: There may be additional env vars the code uses, but if they are undocumented, their use is unsupported.

<table>
  <thead>
    <tr>
      <th>Env Var</th>
      <th>Required</th>
      <th>Type/Format</th>    
      <th>Default</th>    
      <th>Purpose</th>
    </tr>
  </thead>

  <tbody>
    <!-- Flask configs -->
    <tr>
      <td><code>SERVER_NAME</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>Set the server/host name in Flask</td>
    </tr>
    <tr>
      <td><code>SECRET_KEY</code></td>
      <td>true</td>
      <td>string</td>
      <td></td>
      <td>The Flask secret key used for signing cookies.</td>
    </tr>
    <!-- SqlAlchemy configs -->
    <tr>
      <td><code>SQLALCHEMY_DATABASE_URI</code></td>
      <td>true</td>
      <td>URL</td>
      <td></td>
      <td>SqlAlchemy database connection string</td>
    </tr>
    <!-- Hushline configs -->
    <tr>
      <td><code>DIRECTORY_VERIFIED_TAB_ENABLED</code></td>
      <td>false</td>
      <td>boolean</td>
      <td><code>true</code></td>
      <td>
        Enable the "Verified" tab on the Hush Line directory.
        When set to <code>true</code>, the directory shows only verified users with a second tab for all users.
        When set to <code>false</code>, a single tab with all users is displayed.
      </td>
    </tr>
    <tr>
      <td><code>REGISTRATION_CODES_REQUIRED</code></td>
      <td>false</td>
      <td>boolean</td>
      <td><code>true</code></td>
      <td>Whether or not new user registrations require invite codes.</td>
    </tr>
    <tr>
      <td><code>NOTIFICATIONS_ADDRESS</code></td>
      <td>false</td>
      <td>email address</td>
      <td></td>
      <td>Email address to use for sending message notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_FORWARDING_MESSAGE_HTML</code></td>
      <td>false</td>
      <td>HTML</td>
      <td></td>
      <td>Message to display on the Email settings page below the SMTP forwarding config.</td>
    </tr>
    <tr>
      <td><code>SMTP_USERNAME</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>SMTP username for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_PASSWORD</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>SMTP password for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_SERVER</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>SMTP server for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_PORT</code></td>
      <td>false</td>
      <td>integer</td>
      <td></td>
      <td>SMTP port for sending notifications</td>
    </tr>
    <tr>
      <td><code>SMTP_ENCRYPTION</code></td>
      <td>false</td>
      <td>string</td>
      <td>StartTLS</td>
      <td>SMTP encryption method for sending notifications</td>
    </tr>
    <tr>
      <td><code>REQUIRE_PGP</code></td>
      <td>false</td>
      <td>boolean</td>
      <td><code>false</code></td>
      <td>Whether users are required to use PGP to receive messages.</td>
    </tr>
    <tr>
      <td><code>STRIPE_PUBLISHABLE_KEY</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/keys" target="_blank">Stripe publishable key</a> for enabling payments</td>
    </tr>
    <tr>
      <td><code>STRIPE_SECRET_KEY</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/keys" target="_blank">Stripe secret key</a> for enabling payments</td>
    </tr>
    <tr>
      <td><code>STRIPE_WEBHOOK_SECRET</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td><a href="https://docs.stripe.com/webhooks#endpoint-secrets" target="_blank">Stripe webhook key</a> for enabling payments</td>
    </tr>
    <tr>
      <td><code>ONION_HOSTNAME</code></td>
      <td>false</td>
      <td>string</td>
      <td></td>
      <td>Tor Onion Service host name that the Hush Line app is additionally available as.</td>
    </tr>
  </tbody>
</table>

## Customization

To support customization of the app, there are two methods of setting arbitrary config values.

- All values of the form `HL_CFG_*` will have the prefix `HL_CFG_` stripped and will be set as strings in the config. (e.g., `HL_CFG_FOO='bar'` will set the config `FOO` to the string `bar`)
- All values of the form `HL_CFG_JSON_*` will have the prefix `HL_CFG_JSON_` stripped and will be parsed as JSON then set in the config. (e.g., `HL_CFG_FOO='123'` will set the config `FOO` to the int `123` and `HL_CFG_BAZ='"true"'` [note the quotes] will the config `BAZ` to the string `true`)
