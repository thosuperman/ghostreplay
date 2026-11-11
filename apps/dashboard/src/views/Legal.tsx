import type { ReactNode } from "react";
import { href, type LegalPage } from "../lib/router";

/**
 * Terms of Service, Privacy Policy and Disclaimer.
 *
 * The privacy policy describes what this deployment actually does. When the data handling
 * changes (a new cookie, analytics, a new provider, different retention), update this file
 * and LAST_UPDATED in the same change. Sources of truth:
 *   - session cookie, rate limiting, per-session expiry: packages/ghostreplay/src/ghostreplay/server/app.py, settings.py
 *   - access log and its rotation: deploy/lightsail/Caddyfile
 *   - journal retention: deploy/lightsail/server-setup.sh; backups: deploy/lightsail/bin/gr-backup (+ timer)
 *   - public limits: deploy/lightsail/ghostreplay.env
 */

const LAST_UPDATED = "November 12, 2026";
const SITE = "https://ghostreplay.hayaix.tech";
const REPO = "https://github.com/thosuperman/ghostreplay";
const ISSUES = `${REPO}/issues`;

const TITLES: Record<LegalPage, string> = {
  terms: "Terms of Service",
  privacy: "Privacy Policy",
  disclaimer: "Disclaimer",
};

export function Legal({ page }: { page: LegalPage }) {
  return (
    <div className="animate-fade mx-auto max-w-[820px]" data-testid={`legal-${page}`}>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-300/80">Legal</div>
      <h1 className="text-3xl font-bold tracking-tight text-white md:text-4xl">{TITLES[page]}</h1>
      <p className="mt-2 text-sm text-ink-400">Last updated: {LAST_UPDATED}</p>

      <nav className="mt-6 flex flex-wrap gap-2" aria-label="Legal pages">
        {(Object.keys(TITLES) as LegalPage[]).map((p) => (
          <a
            key={p}
            href={href({ name: "legal", page: p })}
            aria-current={p === page ? "page" : undefined}
            className={
              p === page
                ? "rounded-lg bg-white/[0.08] px-3 py-1.5 text-sm font-medium text-white ring-1 ring-white/15"
                : "rounded-lg px-3 py-1.5 text-sm text-ink-300 ring-1 ring-white/10 hover:text-white"
            }
          >
            {TITLES[p]}
          </a>
        ))}
      </nav>

      <div className="mt-8 space-y-10 text-[15px] leading-relaxed text-ink-200">
        {page === "terms" && <Terms />}
        {page === "privacy" && <Privacy />}
        {page === "disclaimer" && <Disclaimer />}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-white">{title}</h2>
      {children}
    </section>
  );
}

function A({ to, children }: { to: string; children: ReactNode }) {
  const external = to.startsWith("http");
  return (
    <a className="text-cyan-300 hover:underline" href={to} {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
      {children}
    </a>
  );
}

function List({ children }: { children: ReactNode }) {
  return <ul className="list-disc space-y-1.5 pl-5">{children}</ul>;
}

function Summary({ children }: { children: ReactNode }) {
  return <div className="rounded-xl bg-white/[0.03] px-5 py-4 text-sm text-ink-200 ring-1 ring-white/10">{children}</div>;
}

function Contact() {
  return (
    <p>
      The only contact channel for this project is its GitHub repository: open an issue at{" "}
      <A to={ISSUES}>{ISSUES.replace("https://", "")}</A>. Issues are public, so do not include personal
      information in them. For a privacy request or anything you would rather not discuss in public, open an issue
      titled “Private contact request” without details, and we will reply there with a private way to continue.
    </p>
  );
}

/* ------------------------------------------------------------------------------------------ */

function Terms() {
  return (
    <>
      <Summary>
        <b className="text-white">In short:</b> GhostReplay Lab is a free, open-source demo of a testing tool for AI
        agents, run as a personal project. Use it to explore and learn, don’t abuse it, and don’t rely on it for anything
        important. It is provided as is.
      </Summary>

      <Section title="1. Who we are and acceptance of these terms">
        <p>
          These Terms of Service (“Terms”) govern your use of the website at <A to={SITE}>{SITE.replace("https://", "")}</A>{" "}
          (the “Site”), operated by the owner of the GhostReplay Lab project (“we”, “us”). By accessing or using the Site
          you agree to these Terms, our <A to={href({ name: "legal", page: "privacy" })}>Privacy Policy</A> and our{" "}
          <A to={href({ name: "legal", page: "disclaimer" })}>Disclaimer</A>. If you do not agree, please do not use the
          Site.
        </p>
        <p>
          The GhostReplay source code is published separately under the MIT License in our{" "}
          <A to={REPO}>GitHub repository</A>. Your use of the code is governed by that license, not by these Terms. These
          Terms cover the hosted Site.
        </p>
      </Section>

      <Section title="2. Permitted use">
        <p>You may use the Site, free of charge and without an account, to:</p>
        <List>
          <li>run the guided demos and the developer views;</li>
          <li>inspect, replay, break and compare the demo executions;</li>
          <li>import GhostReplay trace files for inspection in your own browser session;</li>
          <li>read the documentation and evaluate the software, including for a hackathon or other review.</li>
        </List>
      </Section>

      <Section title="3. Prohibited activities">
        <p>You agree not to:</p>
        <List>
          <li>use the Site for anything unlawful, or to infringe anyone’s rights;</li>
          <li>
            upload trace files containing other people’s personal information, confidential or secret data (such as
            passwords, API keys or customer records), malware, or content you do not have the right to share;
          </li>
          <li>
            attack, probe or overload the Site: for example denial-of-service, automated scraping or high-volume
            requests, circumventing rate limits or session isolation, or trying to reach other visitors’ data;
          </li>
          <li>try to gain unauthorised access to the server, its services or the systems behind it;</li>
          <li>misrepresent the Site, its results or your affiliation with us.</li>
        </List>
        <p>
          The Site never executes code you upload, and it may reject, limit or delete requests and data that break
          these rules. If you find a security issue, please tell us through the contact channel below (without
          details in public) rather than testing it further against the Site.
        </p>
      </Section>

      <Section title="4. Intellectual property">
        <p>
          The GhostReplay software is open source under the MIT License. The Site’s name, logo, ghost icon, design,
          screenshots, demo video and written content are ours unless stated otherwise. You may share links and
          screenshots of the Site for commentary, review, teaching or reporting.
        </p>
        <p>
          Content you upload (trace files) stays yours. You grant us only the limited permission needed to store and
          display it to you during your session, as described in the Privacy Policy. Third-party names and trademarks
          mentioned on the Site (for example Claude, Anthropic, AWS and Kiro) belong to their owners and are used only to
          describe the technology; their use does not imply endorsement.
        </p>
      </Section>

      <Section title="5. Third-party websites and services">
        <p>
          The Site links to third-party websites such as GitHub and YouTube, and it is hosted on third-party
          infrastructure (Amazon Web Services). We do not control third-party sites and are not responsible for their
          content, availability or privacy practices. Your use of them is governed by their own terms.
        </p>
      </Section>

      <Section title="6. Availability and changes to the Site">
        <p>
          The Site is a personal project run on a single small server. It may be slow, unavailable, reset or
          discontinued at any time, with or without notice. We may change, add or remove features, change limits (such
          as rate limits and data retention), or delete stored demo data whenever needed to operate or protect the Site.
        </p>
      </Section>

      <Section title="7. Experimental software">
        <p>
          GhostReplay Lab is experimental software under active development. Features may be incomplete, behave
          unexpectedly or change between versions. The demos use fictional test data and isolated local services. No
          real payment, refund or cloud operation is ever performed. Model decisions shown in the guided demos come from
          recorded AI runs and some are deliberately injected faults, as labelled on the Site.
        </p>
      </Section>

      <Section title="8. No warranties">
        <p>
          To the extent permitted by applicable law, the Site and everything on it are provided “as is” and “as
          available”, without warranties of any kind, express or implied, including warranties of merchantability,
          fitness for a particular purpose, accuracy, reliability, availability and non-infringement. We do not warrant
          that the Site will be uninterrupted, secure or error-free, or that results shown on it are correct.
        </p>
      </Section>

      <Section title="9. Limitation of liability">
        <p>
          To the extent permitted by applicable law, we are not liable for any indirect, incidental, special,
          consequential or punitive damages, or for any loss of data, profits, revenue or business, arising out of or in
          connection with the Site or these Terms, even if we were advised of the possibility of such damages. The Site
          is provided free of charge, and our total liability for any claim relating to it is limited to the maximum
          extent permitted by law.
        </p>
        <p>
          Nothing in these Terms excludes or limits liability that cannot be excluded or limited under applicable law,
          including liability for wilful misconduct or gross negligence, or any rights you have as a consumer under
          mandatory law (including Japan’s Consumer Contract Act, where it applies).
        </p>
      </Section>

      <Section title="10. Your responsibilities">
        <List>
          <li>You are responsible for the data you upload and for having the right to upload it.</li>
          <li>
            You are responsible for how you use anything you learn or copy from the Site, including the code, and for
            testing it before relying on it in your own systems.
          </li>
          <li>Verify any result independently before making decisions based on it (see the Disclaimer).</li>
        </List>
      </Section>

      <Section title="11. Changes to these Terms">
        <p>
          We may update these Terms from time to time. The “Last updated” date at the top shows the current version, and
          the change history is public in the repository. Continued use of the Site after a change means you accept the
          updated Terms.
        </p>
      </Section>

      <Section title="12. Governing law">
        <p>
          These Terms are governed by the laws of Japan, without regard to conflict-of-laws rules, and subject to any
          mandatory laws that apply to you where you live. Any dispute will be handled by the competent courts of Japan,
          except where mandatory law gives you the right to bring proceedings elsewhere.
        </p>
      </Section>

      <Section title="13. Contact">
        <Contact />
      </Section>
    </>
  );
}

/* ------------------------------------------------------------------------------------------ */

function Privacy() {
  return (
    <>
      <Summary>
        <b className="text-white">In short:</b> no account, no analytics, no advertising and no tracking cookies. We set
        one cookie to keep your demo runs private to your browser. Like almost every website, our web server logs your
        IP address and browser details for security and operations. Your runs and any trace you upload are deleted from
        the live system after 24 hours, and from backups within about 14 days. This site never sends your data to an AI
        provider.
      </Summary>

      <Section title="1. Scope and who is responsible">
        <p>
          This policy explains how personal information is handled on <A to={SITE}>{SITE.replace("https://", "")}</A>{" "}
          (the “Site”). The Site is operated by the owner of the GhostReplay Lab project (“we”, “us”), who is responsible
          for the information described here. We handle personal information in line with Japan’s Act on the Protection
          of Personal Information (APPI) and other laws that apply.
        </p>
        <p>
          It covers the hosted Site only. If you run GhostReplay yourself from the open-source code, the data stays on
          your own machines, and we receive nothing.
        </p>
      </Section>

      <Section title="2. What we collect">
        <p>We have checked the Site’s code and server configuration. This is everything it collects:</p>
        <div className="overflow-x-auto rounded-xl ring-1 ring-white/10">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-ink-400">
              <tr>
                <th className="px-4 py-2.5 font-medium">Data</th>
                <th className="px-4 py-2.5 font-medium">Why</th>
                <th className="px-4 py-2.5 font-medium">How long</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06] align-top">
              <tr>
                <td className="px-4 py-3"><b className="text-white">Session cookie</b> (<code className="font-mono text-[13px]">gr_session</code>): a random identifier, not linked to your identity</td>
                <td className="px-4 py-3">Keeps the executions you create private to your browser, so other visitors cannot see them</td>
                <td className="px-4 py-3">Expires after 24 hours</td>
              </tr>
              <tr>
                <td className="px-4 py-3"><b className="text-white">Web server access logs</b>: IP address and port, date and time, requested URL and method, response status and size, timing, request headers such as user-agent (browser and OS), TLS details. Cookie and authorization values are redacted by the web server</td>
                <td className="px-4 py-3">Operating the Site, security, abuse prevention and troubleshooting</td>
                <td className="px-4 py-3">Rotated and deleted after at most 14 days</td>
              </tr>
              <tr>
                <td className="px-4 py-3"><b className="text-white">IP address for rate limiting</b>, held in memory only</td>
                <td className="px-4 py-3">Limits how many runs one address can start per minute</td>
                <td className="px-4 py-3">About one minute; never written to disk</td>
              </tr>
              <tr>
                <td className="px-4 py-3"><b className="text-white">Your demo executions</b>: the runs, replays and fault injections you start, stored with a one-way hash of your session identifier</td>
                <td className="px-4 py-3">Showing you your own results</td>
                <td className="px-4 py-3">Deleted from the live database after 24 hours; nightly backups are kept up to 14 days</td>
              </tr>
              <tr>
                <td className="px-4 py-3"><b className="text-white">Trace files you choose to import</b></td>
                <td className="px-4 py-3">Letting you inspect your own trace. Secret-looking values (keys, tokens, card numbers) are redacted before storage</td>
                <td className="px-4 py-3">Same as executions: 24 hours live, backups up to 14 days</td>
              </tr>
              <tr>
                <td className="px-4 py-3"><b className="text-white">Service logs</b>: errors and health checks; no request or visitor details are logged by the lab services</td>
                <td className="px-4 py-3">Keeping the Site running</td>
                <td className="px-4 py-3">Up to 30 days</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>
          We do not ask for your name, email address or any account details, and the demos use only fictional test data.
          An IP address on its own usually does not identify you. We treat it as personal information where it could be
          linked to you, and we never try to identify individual visitors from it.
        </p>
        <p>
          Please do not put personal information into trace files you import. If you do, it is handled as described in
          this policy.
        </p>
      </Section>

      <Section title="3. How we use it">
        <List>
          <li>To provide the Site and show you your own demo results.</li>
          <li>To protect the Site and its visitors: rate limiting, detecting abuse and investigating security incidents.</li>
          <li>To fix errors and keep the service available.</li>
        </List>
        <p>
          We do not sell, rent or share personal information for marketing, and we do not use it for profiling,
          advertising or automated decisions about you.
        </p>
      </Section>

      <Section title="4. Cookies and local storage">
        <p>
          The Site sets one strictly necessary first-party cookie, <code className="font-mono">gr_session</code>. It is
          HttpOnly (not readable by scripts), Secure (sent only over HTTPS) and SameSite=Lax, and it expires after 24
          hours. Only a one-way hash of it is stored on the server. Blocking it does not stop you from using the Site, but
          your runs may not stay private to your browser.
        </p>
        <p>
          The Site does not use localStorage, sessionStorage, IndexedDB, tracking pixels, advertising cookies or browser
          fingerprinting. Fonts and scripts are served from this Site itself, not from third-party content networks.
        </p>
      </Section>

      <Section title="5. Analytics">
        <p>
          We do not use any analytics service (no Google Analytics or similar). Aggregate figures we look at, such as
          the number of stored executions, come from the Site’s own database and logs.
        </p>
      </Section>

      <Section title="6. Third-party providers">
        <List>
          <li>
            <b className="text-white">Amazon Web Services (AWS)</b> hosts the Site (an Amazon Lightsail server and Amazon
            Route 53 DNS). The server and all data described above are located in the United States (us-east-1
            region). AWS provides the infrastructure. Under its service terms it does not access or use the content we
            store, except as needed to provide the service or comply with law.
          </li>
          <li>
            <b className="text-white">Links to GitHub and YouTube.</b> Links to the source code, documentation and demo
            video open those sites, which handle your data under their own privacy policies. Nothing from GitHub or
            YouTube is embedded in the Site, so they receive nothing until you click.
          </li>
        </List>
        <p>
          We do not provide personal information to any other third party, except where required by law (for example a
          valid legal request from authorities) or where APPI otherwise permits it.
        </p>
      </Section>

      <Section title="7. AI-related data processing">
        <p>
          The model decisions shown in the guided demos are recordings of real runs with Anthropic’s Claude models,
          which we made ourselves using fictional test data before publishing them. When you use the Site, those
          recordings are replayed. <b className="text-white">The Site makes no calls to any AI model provider, and
          nothing you do or upload is sent to Anthropic or any other AI service.</b> The services that run the demos
          have no network access beyond the server itself, so they cannot reach outside AI services.
        </p>
        <p>
          The open-source code has an optional live mode that calls a model provider using the operator’s own API key.
          It is disabled on this Site. If you enable it on your own installation, your data goes to the provider you
          configure under that provider’s terms.
        </p>
      </Section>

      <Section title="8. Retention and deletion">
        <List>
          <li>Executions and imported traces: removed from the live database 24 hours after they are created.</li>
          <li>Database backups: taken nightly and kept for 14 days, then deleted automatically.</li>
          <li>Web server access logs: rotated and deleted after at most 14 days.</li>
          <li>Service logs: kept up to 30 days.</li>
        </List>
        <p>
          You can also simply stop using the Site and clear the cookie in your browser. Because we do not know who you
          are, we can only find your data if you give us details that identify it, such as an execution ID.
        </p>
      </Section>

      <Section title="9. Security">
        <List>
          <li>HTTPS only, with HSTS and a strict Content Security Policy.</li>
          <li>Each visitor’s runs are isolated by session, and only a hash of the session identifier is stored.</li>
          <li>Secret-looking values are redacted before any trace or execution is stored.</li>
          <li>
            The demo services run as separate sandboxed system services with no network access beyond the machine
            itself, so they cannot reach cloud metadata, AWS APIs or other external systems.
          </li>
          <li>
            Rate limits, request size limits and storage caps. Administrative access requires SSH keys from
            allowlisted addresses.
          </li>
        </List>
        <p>
          No system is perfectly secure. If we become aware of a breach that affects your personal information, we will
          take the steps required by APPI, including notifying the Personal Information Protection Commission and
          affected individuals where required.
        </p>
      </Section>

      <Section title="10. International data transfers">
        <p>
          The Site is operated from Japan, and its server is in the United States. The United States has no single
          comprehensive federal privacy law equivalent to APPI. Personal information is protected there by federal and
          state laws that vary by sector and state. Because AWS only provides the infrastructure and does not handle the
          content, we do not treat this as providing your data to a third party. We protect it with the measures in
          section 9. If you access the Site from elsewhere, your requests travel over the internet to the United States.
        </p>
      </Section>

      <Section title="11. Your rights">
        <p>
          Under APPI, and other privacy laws that may apply to you (such as the GDPR if you are in the EU or UK), you may
          ask us to:
        </p>
        <List>
          <li>disclose the personal information we hold about you, and any records of providing it to third parties;</li>
          <li>correct, add to or delete it;</li>
          <li>stop using it or stop providing it to third parties.</li>
        </List>
        <p>
          Most data here is deleted automatically within days, and we cannot link it to you without details you give us.
          To make a request, use the contact channel below and include enough information (for example the approximate
          time and the execution IDs) for us to find it. We will respond within a reasonable time and as required by law.
          You may also complain to the Personal Information Protection Commission of Japan, or to the authority where you
          live.
        </p>
        <p>
          The Site is not directed at children. We do not knowingly collect information from children.
        </p>
      </Section>

      <Section title="12. Changes to this policy">
        <p>
          If our data handling changes, for example a new cookie, provider or retention period, we will update this
          policy and the “Last updated” date before or when the change takes effect. Its history is public in the
          repository.
        </p>
      </Section>

      <Section title="13. Contact and privacy inquiries">
        <Contact />
      </Section>
    </>
  );
}

/* ------------------------------------------------------------------------------------------ */

function Disclaimer() {
  return (
    <>
      <Summary>
        <b className="text-white">In short:</b> this is a personal, experimental project for learning and evaluation.
        It is not a production service, nothing on it is professional advice, and anything involving AI can be wrong.
        Check results yourself before relying on them.
      </Summary>

      <Section title="A personal, experimental project">
        <p>
          GhostReplay Lab is a personal hobby project, built in the open and entered in a hackathon. It is not a
          commercial product. No company stands behind it, it carries no service level, and no support is guaranteed.
        </p>
        <p>
          The software and the Site are provided for informational, educational and experimental purposes. The demo
          scenarios (refunds, servers, invoices) are simulations with fictional data. They show how a class of failure
          can happen and be tested, not how any real company’s systems work.
        </p>
      </Section>

      <Section title="No guarantees">
        <p>
          We make no guarantee that the Site, the software or any result, measurement, verdict or explanation shown on
          them is accurate, complete, reliable, current, available or fit for a particular purpose. A passing check or a
          “fix proven” verdict means the specific scenario passed under the specific conditions shown. It does not mean
          your system is safe. Test any code or approach in your own environment before using it.
        </p>
        <p>
          Nothing on the Site is legal, financial, security or other professional advice. The Site is provided as is. See
          the <A to={href({ name: "legal", page: "terms" })}>Terms of Service</A> for the full warranty disclaimer and
          limitation of liability.
        </p>
      </Section>

      <Section title="AI-generated content">
        <List>
          <li>
            <b className="text-white">AI output may contain errors.</b> Model decisions and messages shown on the Site
            were produced by an AI model (Anthropic’s Claude) and recorded. AI output can be wrong, incomplete or
            misleading, even when it sounds confident.
          </li>
          <li>
            <b className="text-white">Some decisions are injected on purpose.</b> To test how a workflow behaves when a
            model makes a bad choice, some decisions are replaced with deliberately unsafe ones. These are always
            labelled “injected”, and they do not represent what the model actually said.
          </li>
          <li>
            <b className="text-white">Verify independently.</b> Treat any AI output, and any explanation derived from
            it, as a starting point to check, not as a fact or an instruction to act on.
          </li>
          <li>
            <b className="text-white">AI services change.</b> Model providers can change, retire or restrict models and
            APIs at any time. Recordings reflect one model at one point in time, a live run today could behave
            differently, and the optional live mode may stop working if a provider changes its service.
          </li>
        </List>
      </Section>

      <Section title="External links and trademarks">
        <p>
          Links to third-party sites are provided for convenience. We are not responsible for their content. Product
          names such as Claude, Anthropic, AWS, GitHub, YouTube and Kiro are trademarks of their owners, used only to
          describe the technology. GhostReplay Lab is not affiliated with or endorsed by them.
        </p>
      </Section>

      <Section title="Contact">
        <Contact />
      </Section>
    </>
  );
}
