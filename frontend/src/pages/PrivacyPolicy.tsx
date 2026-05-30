import { Link } from 'react-router-dom'
import { ArrowLeft, Shield } from 'lucide-react'

const LAST_UPDATED = 'May 29, 2026'
const CONTACT_EMAIL = 'privacy@clozehive.com'
const APP_NAME = 'ClozéHive'
const COMPANY_NAME = 'ClozéHive, Inc.'

export default function PrivacyPolicy() {
  return (
    <div className="min-h-screen bg-cream-50 dark:bg-slate-950 px-4 py-12">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="mb-10 space-y-4">
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700
                       dark:text-slate-400 dark:hover:text-slate-200 transition"
          >
            <ArrowLeft size={14} /> Back
          </Link>

          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center shrink-0">
              <Shield size={20} className="text-brand-600 dark:text-brand-400" />
            </div>
            <div>
              <h1 className="font-display font-bold text-2xl text-slate-900 dark:text-white">
                Privacy Policy
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Last updated: {LAST_UPDATED}
              </p>
            </div>
          </div>

          <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
            {COMPANY_NAME} ("{APP_NAME}", "we", "us", or "our") is committed to protecting your
            personal information. This Privacy Policy explains what data we collect, how we use it,
            and your rights regarding that data.
          </p>
        </div>

        {/* Body */}
        <div className="space-y-8 text-slate-700 dark:text-slate-300 leading-relaxed">

          <Section title="1. Information We Collect">
            <Subsection title="Information you provide">
              <ul className="list-disc list-inside space-y-1 text-sm">
                <li>Account details: name, email address, and password (stored as a bcrypt hash)</li>
                <li>Style profile: preferred styles, colors, body measurements you choose to enter</li>
                <li>Clothing items: photos, descriptions, tags, and metadata you upload to your closet</li>
                <li>Chat messages you send to the AI stylist (FANI)</li>
                <li>Travel plans and packing lists you create</li>
              </ul>
            </Subsection>
            <Subsection title="Information collected automatically">
              <ul className="list-disc list-inside space-y-1 text-sm">
                <li>Usage data: pages visited, features used, session duration</li>
                <li>Device information: browser type, operating system, screen resolution</li>
                <li>IP address (used for rate limiting and fraud prevention only)</li>
                <li>Authentication tokens stored in HttpOnly cookies</li>
              </ul>
            </Subsection>
            <Subsection title="Third-party sign-in">
              <p className="text-sm">
                If you sign in with Google, we receive your name, email address, and profile picture
                from Google. We do not receive your Google password or access other Google data.
              </p>
            </Subsection>
          </Section>

          <Section title="2. How We Use Your Information">
            <ul className="list-disc list-inside space-y-1 text-sm">
              <li>Provide and improve the {APP_NAME} service</li>
              <li>Generate AI-powered outfit recommendations using your closet items</li>
              <li>Create vector embeddings of your style preferences for semantic search (stored in our database, not shared)</li>
              <li>Send transactional emails (password resets, account notifications)</li>
              <li>Detect and prevent abuse, fraud, and security incidents</li>
              <li>Analyze aggregate usage patterns to improve product features (anonymised)</li>
            </ul>
            <p className="text-sm mt-3">
              We do <strong>not</strong> sell your personal data or clothing photos to third parties.
              We do <strong>not</strong> use your data to train AI models without your explicit consent.
            </p>
          </Section>

          <Section title="3. AI Processing & Third-Party Models">
            <p className="text-sm">
              {APP_NAME} uses large language models (currently OpenAI GPT-4o and Google Gemini) to
              power outfit recommendations and the AI stylist chat. When you interact with these
              features, relevant portions of your style profile and chat messages are sent to these
              providers for processing. This processing is governed by OpenAI's and Google's enterprise
              data processing agreements. Neither provider uses your data to train their models under
              our enterprise agreements.
            </p>
            <p className="text-sm mt-2">
              Your clothing photos may be processed by AI vision APIs for automatic tagging. Photo
              data is transmitted securely and is not stored by the AI provider beyond the API request.
            </p>
          </Section>

          <Section title="4. Data Storage & Security">
            <ul className="list-disc list-inside space-y-1 text-sm">
              <li>Data is stored in PostgreSQL databases with encryption at rest</li>
              <li>Photos are stored in secured cloud object storage with access controls</li>
              <li>All data transmission uses TLS 1.2 or higher</li>
              <li>Authentication uses HttpOnly, Secure, SameSite cookies to prevent XSS and CSRF attacks</li>
              <li>We conduct regular security reviews of our infrastructure</li>
            </ul>
          </Section>

          <Section title="5. Data Retention">
            <p className="text-sm">
              We retain your data for as long as your account is active. If you delete your account,
              we will permanently delete all your personal data, closet items, and chat history within
              30 days, except where retention is required by law.
            </p>
          </Section>

          <Section title="6. Your Rights">
            <p className="text-sm mb-2">
              Depending on your jurisdiction, you may have the following rights:
            </p>
            <ul className="list-disc list-inside space-y-1 text-sm">
              <li><strong>Access:</strong> Request a copy of all personal data we hold about you</li>
              <li><strong>Correction:</strong> Update inaccurate personal information</li>
              <li><strong>Deletion:</strong> Request deletion of your account and all associated data</li>
              <li><strong>Portability:</strong> Export your closet data in a machine-readable format</li>
              <li><strong>Objection:</strong> Opt out of non-essential processing</li>
              <li><strong>GDPR / CCPA:</strong> EU and California residents have additional rights under applicable law</li>
            </ul>
            <p className="text-sm mt-3">
              To exercise any of these rights, contact us at{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-brand-600 dark:text-brand-400 hover:underline">
                {CONTACT_EMAIL}
              </a>.
            </p>
          </Section>

          <Section title="7. Cookies">
            <p className="text-sm">
              We use strictly necessary cookies for authentication (HttpOnly refresh token cookie).
              We do not use advertising cookies or third-party tracking cookies. We may use anonymous
              analytics in the future — we will update this policy and notify you before doing so.
            </p>
          </Section>

          <Section title="8. Children's Privacy">
            <p className="text-sm">
              {APP_NAME} is not directed to children under 13. We do not knowingly collect personal
              information from children under 13. If you believe a child has provided us with their
              information, please contact us immediately.
            </p>
          </Section>

          <Section title="9. Changes to This Policy">
            <p className="text-sm">
              We may update this Privacy Policy from time to time. We will notify you of material
              changes by email and by displaying a notice in the app at least 30 days before changes
              take effect. Continued use of {APP_NAME} after changes take effect constitutes acceptance
              of the updated policy.
            </p>
          </Section>

          <Section title="10. Contact">
            <p className="text-sm">
              For privacy-related questions or requests, contact us at:
            </p>
            <address className="text-sm not-italic mt-2 space-y-0.5">
              <div className="font-medium">{COMPANY_NAME}</div>
              <div>
                Email:{' '}
                <a href={`mailto:${CONTACT_EMAIL}`} className="text-brand-600 dark:text-brand-400 hover:underline">
                  {CONTACT_EMAIL}
                </a>
              </div>
            </address>
          </Section>

        </div>

        {/* Footer nav */}
        <div className="mt-12 pt-6 border-t border-slate-200 dark:border-white/10 flex flex-wrap gap-4 text-sm text-slate-500 dark:text-slate-400">
          <Link to="/terms" className="hover:text-brand-600 dark:hover:text-brand-400 transition">Terms of Service</Link>
          <Link to="/login" className="hover:text-brand-600 dark:hover:text-brand-400 transition">Sign In</Link>
          <a href={`mailto:${CONTACT_EMAIL}`} className="hover:text-brand-600 dark:hover:text-brand-400 transition">Contact</a>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="font-display font-semibold text-lg text-slate-800 dark:text-white">{title}</h2>
      {children}
    </section>
  )
}

function Subsection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="font-medium text-sm text-slate-700 dark:text-slate-200">{title}</h3>
      {children}
    </div>
  )
}
