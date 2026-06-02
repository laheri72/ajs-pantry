# Professional SEO & Redirection Guide

To ensure your website is fully compliant with Google policies and avoids being flagged as "malicious" or "phishing" due to blind redirects, please follow these steps.

## 1. The Problem: Blind Redirects
Currently, `https://ajs-pantry.web.app/` redirects **everything** directly to the login page.
*   **Googlebot Error:** When Google tries to find your verification file (`google0cbc...html`) or sitemap, it is redirected to the login page. Since it can't find the file, verification fails.
*   **Security Flag:** Search engines often flag "blind redirects to a login page" as suspicious behavior (cloaking).

## 2. The Solution: Path-Preserving Redirects
You must configure Firebase to redirect users to the **same path** on your new server.
Example: `ajs-pantry.web.app/sitemap.xml` should go to `140-245-12-63.sslip.io/sitemap.xml`.

### How to apply:
I have created a `firebase.json` in your project root. If you use the Firebase CLI, simply run:
```bash
firebase deploy --only hosting
```

**If you use the Firebase Console manually:**
1. Go to **Hosting** > **Redirects**.
2. Update your redirect rule:
    *   **Source:** `/:path*`
    *   **Destination:** `https://140-245-12-63.sslip.io/:path*`
    *   **Type:** 301 (Permanent)

## 3. Why this works
1.  **Verification:** Google will be able to hit `ajs-pantry.web.app/google0cbc51477636a185.html`, which will redirect to `140-245-12-63.sslip.io/google0cbc51477636a185.html`. My code is already set up to serve this file correctly.
2.  **Sitemaps:** Crawlers will find the sitemap and index your site professionally.
3.  **Canonical URLs:** I have added `<link rel="canonical">` tags to your site. This tells Google: "Even if you are on the sslip.io IP, the official home of this content is the web.app domain." This builds "Domain Authority" for your brand.

## 4. Next Steps
Once you update the redirect in Firebase:
1.  Go to **Google Search Console**.
2.  Add the property `https://ajs-pantry.web.app/`.
3.  Verify ownership (it should now pass!).
4.  Submit the sitemap: `https://ajs-pantry.web.app/sitemap.xml`.
