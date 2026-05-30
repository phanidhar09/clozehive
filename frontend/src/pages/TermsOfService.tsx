import { Link } from 'react-router-dom'
import { ArrowLeft, FileText } from 'lucide-react'

const LAST_UPDATED = 'May 29, 2026'
const CONTACT_EMAIL = 'legal@clozehive.com'
const APP_NAME = 'ClozéHive'
const COMPANY_NAME = 'ClozéHive, Inc.'

export default function TermsOfService() {
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
            <div className="w-10 h-10 rounded-xl bg-highlight-100 dark:bg-highlight-700/30 flex items-center justify-center shrink-0">
              <FileText size={20} className="text-highlight-600 dark:text-highlight-400" />
            </div>
            <div>
              <h1 className="font-display font-bold text-2xl text-slate-900 dark:text-white">
                Terms of Service
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Last updated: {LAST_UPDATED}
              </p>
            </div>
          </div>

          <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
            Please read these Terms of Service carefully before using {APP_NAME}. By creating an
            account or using the service, you agree to be bound by these terms.
          </p>
        </div>

        {/* Body */}
        <div className="space-y-8 text-slate-700 dark:text-slate-300 leading-relaxed">

          <Section title="1. Acceptance of Terms">
            <p className="text-sm">
              By accessing or using {APP_NAME} (the "Service"), operated by {COMPANY_NAME} ("we",
              "us", or "our"), you agree to these Terms of Service and our{' '}
              <Link to="/privacy" className="text-brand-600 dark:text-brand-400 hover:underline">
                Privacy Policy
              </Link>
              . If you do not agree, do not use the Service.
            </p>
          </Section>

          <Section title="2. Eligibility">
            <p className="text-sm">
              You must be at least 13 years old to use {APP_NAME}. If you are between 13 and 18,
              you must have permission from a parent or guardian. By using the Service, you represent
              that you meet these requirements.
            </p>
          </Section>

          <Section title="3. Your Account">
            <ul className="list-disc list-inside space-y-1 text-sm">
              <li>You are responsible for maintaining the confidentiality of your account credentials</li>
              <li>You are responsible for all activity that occurs under your account</li>
              <li>You must provide accurate and current information when creating your account</li>
              <li>You may not share your account with others or create multiple accounts to circumvent restrictions</li>
              <li>Notify us immediately at{' '}
                <a href={`mailto:${CONTACT_EMAIL}`} className="text-brand-600 dark:text-brand-400 hover:underline">
                  {CONTACT_EMAIL}
                </a>{' '}
                if you suspect unauthorized access to your account
              </li>
            </ul>
          </Section>

          <Section title="4. Acceptable Use">
            <p className="text-sm mb-2">You agree not to:</p>
            <ul className="list-disc list-inside space-y-1 text-sm">
              <li>Upload content that is illegal, harmful, obscene, or infringes third-party rights</li>
              <li>Attempt to reverse-engineer, scrape, or extract data from the Service in bulk</li>
              <li>Use the Service to train AI/ML models without written permission</li>
              <li>Attempt to circumvent rate limits, security measures, or access controls</li>
              <li>Impersonate another person or entity</li>
              <li>Use the Service for any commercial purpose without our written consent</li>
              <li>Upload malicious code or interfere with the Service's operation</li>
            </ul>
          </Section>

          <Section title="5. Your Content">
            <p className="text-sm">
              You retain ownership of all content you upload to {APP_NAME} ("Your Content"),
              including clothing photos, descriptions, and style data. By uploading content, you
              grant us a limited, non-exclusive, worldwide license to store, process, and display
              Your Content solely to provide the Service to you.
            </p>
            <p className="text-sm mt-2">
              We do not claim ownership of Your Content and will not sell it to third parties.
              You can delete Your Content or your entire account at any time.
            </p>
            <p className="text-sm mt-2">
              You represent that you have all necessary rights to upload Your Content and that it
              does not violate any applicable laws or third-party rights.
            </p>
          </Section>

          <Section title="6. AI-Generated Recommendations">
            <p className="text-sm">
              {APP_NAME} uses artificial intelligence to provide outfit suggestions, style
              recommendations, and shopping advice. These are suggestions only — they do not
              constitute professional fashion, financial, or lifestyle advice. AI recommendations
              may occasionally be inaccurate, inappropriate, or not reflect your preferences.
            </p>
            <p className="text-sm mt-2">
              We are not liable for any decisions you make based on AI-generated recommendations,
              including purchases.
            </p>
          </Section>

          <Section title="7. Subscription & Payments">
            <p className="text-sm">
              {APP_NAME} offers a free tier and paid subscription plans. By subscribing to a paid
              plan, you agree to pay the applicable fees. Subscriptions auto-renew unless cancelled.
              You may cancel at any time from your account settings; cancellation takes effect at
              the end of the current billing period. We do not offer refunds for partial billing
              periods except where required by law.
            </p>
            <p className="text-sm mt-2">
              We may change subscription prices with 30 days' notice. Continued use after a price
              change takes effect constitutes acceptance of the new price.
            </p>
          </Section>

          <Section title="8. Intellectual Property">
            <p className="text-sm">
              The {APP_NAME} Service, including its design, code, AI models, and features, is owned
              by {COMPANY_NAME} and protected by copyright, trademark, and other intellectual
              property laws. You may not copy, modify, distribute, or create derivative works of
              any part of the Service without our written permission.
            </p>
          </Section>

          <Section title="9. Privacy">
            <p className="text-sm">
              Your use of the Service is also governed by our{' '}
              <Link to="/privacy" className="text-brand-600 dark:text-brand-400 hover:underline">
                Privacy Policy
              </Link>
              , which is incorporated into these Terms by reference.
            </p>
          </Section>

          <Section title="10. Disclaimer of Warranties">
            <p className="text-sm">
              THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND,
              EXPRESS OR IMPLIED. WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED,
              ERROR-FREE, OR THAT AI RECOMMENDATIONS WILL BE ACCURATE. YOUR USE OF THE SERVICE
              IS AT YOUR SOLE RISK.
            </p>
          </Section>

          <Section title="11. Limitation of Liability">
            <p className="text-sm">
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, {COMPANY_NAME.toUpperCase()} AND ITS
              AFFILIATES SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL,
              OR PUNITIVE DAMAGES ARISING FROM YOUR USE OF THE SERVICE. OUR TOTAL LIABILITY TO YOU
              FOR ANY CLAIMS SHALL NOT EXCEED THE AMOUNT YOU PAID US IN THE 12 MONTHS PRECEDING
              THE CLAIM.
            </p>
          </Section>

          <Section title="12. Termination">
            <p className="text-sm">
              We may suspend or terminate your account if you violate these Terms. You may delete
              your account at any time from Profile settings. Upon termination, your right to use
              the Service ceases and we will delete your data per our{' '}
              <Link to="/privacy" className="text-brand-600 dark:text-brand-400 hover:underline">
                Privacy Policy
              </Link>.
            </p>
          </Section>

          <Section title="13. Changes to Terms">
            <p className="text-sm">
              We may update these Terms at any time. We will notify you of material changes by
              email and in-app notice at least 30 days before they take effect. Continued use of
              the Service after changes take effect constitutes your acceptance of the new Terms.
            </p>
          </Section>

          <Section title="14. Governing Law">
            <p className="text-sm">
              These Terms are governed by the laws of the State of Delaware, United States, without
              regard to conflict-of-law principles. Any dispute arising from these Terms shall be
              resolved in the state or federal courts located in Delaware.
            </p>
          </Section>

          <Section title="15. Contact">
            <p className="text-sm">
              For questions about these Terms, contact us at:
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
          <Link to="/privacy" className="hover:text-brand-600 dark:hover:text-brand-400 transition">Privacy Policy</Link>
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
