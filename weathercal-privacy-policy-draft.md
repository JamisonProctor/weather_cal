# WeatherCal Privacy Policy

**Last updated:** March 9, 2026

WeatherCal ("we", "us", "the Service") is a personal weather calendar service operated by Jamison Proctor. This privacy policy explains what data we collect, how we use it, and your rights regarding that data.

WeatherCal is currently a prototype product under active development. By using the Service, you acknowledge that features may change, and we may contact you at the email address you provided regarding service updates, changes, or issues that affect your account.

## What Data We Collect

### Account Data
When you sign up, we collect your **email address** and store a **hashed version of your password** (we never store your password in plain text). We also record when your account was created.

### Location Data
To generate your weather calendar, we store the **city or location name** you provide, along with its **latitude, longitude, and timezone**. This is necessary to fetch accurate weather forecasts for your area.

### Calendar Feed Data
We generate a unique, random **feed token** for your calendar subscription. We log when your calendar app polls the feed, including the **timestamp, user agent string** (which identifies your calendar app), and **IP address**. This helps us monitor service health and diagnose issues.

### Weather Preferences
We store your **weather display preferences**, including temperature thresholds, warning types, temperature unit, and event display settings. These are used solely to customize your calendar feed.

### Feedback Data
If you submit feedback through the app, we collect the **content of your feedback** along with basic technical context (browser user agent, platform, screen size, timezone) to help us understand and reproduce any issues you report.

### Google Calendar Data (Optional)
If you choose to connect your Google account, we request access using the `calendar.app.created` scope. This scope **only** allows us to create and manage a calendar that WeatherCal itself created in your Google account. We **cannot** read, modify, or delete any of your existing calendars or events.

When you connect Google, we store your **OAuth access token, refresh token, token expiry**, and the **calendar ID** of the WeatherCal calendar we create. These are used solely to push weather events to your Google Calendar.

## How We Use Your Data

We use your data exclusively to provide and maintain the WeatherCal service:

- Your **email** identifies your account and allows us to contact you about service-related matters
- Your **location** is sent to weather data providers to fetch forecasts (as coordinates only, not linked to your identity)
- Your **preferences** customize which weather events and warnings appear in your calendar
- Your **feed token** authenticates your calendar app when it requests your ICS feed
- Your **Google tokens** (if connected) push weather events to a dedicated WeatherCal calendar in your Google account
- **Poll logs** help us monitor whether calendar subscriptions are working correctly

## How We Store Your Data

All data is stored in a SQLite database on our server. Passwords are hashed using bcrypt. Google OAuth tokens are stored server-side and are never exposed to the browser. The service runs on a single server and data is not replicated to other locations.

## What We Share

We do **not** sell, rent, or share your personal data with third parties.

Your location coordinates (latitude and longitude) are sent to third-party weather APIs to retrieve forecast data. These requests do not include your email, name, or any other identifying information.

Google OAuth tokens are used exclusively to communicate with Google's Calendar API on your behalf.

## Your Rights and Controls

### Access and Update
You can view and update your email address, password, location, and weather preferences at any time through your account settings.

### Delete Your Account
You can delete your account through the settings page. When you delete your account, we immediately revoke your feed token (stopping calendar updates), and your account is deactivated. If you have connected Google Calendar, disconnecting will revoke the OAuth tokens and remove our access to the calendar we created.

### Disconnect Google Calendar
You can disconnect your Google account at any time through the settings page. This revokes our access tokens and stops event updates to your Google Calendar. The WeatherCal calendar created in your Google account will remain (since you own it), but we will no longer be able to update it.

### Data Portability
Your weather calendar is available as a standard ICS feed that any calendar application can subscribe to. You can export this data at any time simply by accessing your feed URL.

### GDPR Rights (EU Users)
If you are located in the European Union, you have the right to access, correct, delete, or port your personal data. You also have the right to object to or restrict processing. To exercise these rights, contact us at the email address listed below.

## Cookies and Tracking

WeatherCal uses a **session cookie** to keep you logged in. We do not use analytics cookies, advertising trackers, or any third-party tracking scripts.

## Prototype Disclaimer

WeatherCal is a prototype product under active development. The Service is provided "as is" without warranty. Features may change, be added, or be removed. We may contact you at the email address associated with your account regarding updates, changes, outages, or feedback requests related to the Service.

## Changes to This Policy

We may update this privacy policy as the service evolves. Significant changes will be communicated via the email address associated with your account.

## Contact

For any questions about this privacy policy or your data, contact:

Jamison Proctor
jamison.proctor@gmail.com
