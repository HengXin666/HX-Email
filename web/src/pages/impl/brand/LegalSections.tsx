import React from "react";
import { CONTACT_EMAIL } from "./i18n";
import type { LegalSection } from "./privacyContent";

interface LegalSectionsProps {
  sections: LegalSection[];
  contactLabel: string;
}

export const LegalSections: React.FC<LegalSectionsProps> = ({ sections, contactLabel }) => (
  <>
    {sections.map((section, index) => (
      <section key={section.heading}>
        <h2 className="mb-3 mt-9 text-xl text-gh-text">{section.heading}</h2>
        {section.paragraphs?.map((paragraph) => (
          <p key={paragraph} className="mb-3.5">
            {paragraph}
          </p>
        ))}
        {section.list && (
          <ul className="mb-3.5 list-disc pl-[22px]">
            {section.list.map((item) => (
              <li key={item} className="mb-1.5">
                {item}
              </li>
            ))}
          </ul>
        )}
        {section.highlight && (
          <div className="mb-3.5 rounded-[10px] border border-gh-border bg-gh-canvas-subtle p-5 text-sm text-gh-text-muted">
            {section.highlight}
          </div>
        )}
        {index === sections.length - 1 && (
          <p>
            {contactLabel}{" "}
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="text-gh-accent transition hover:underline"
            >
              {CONTACT_EMAIL}
            </a>
          </p>
        )}
      </section>
    ))}
  </>
);
