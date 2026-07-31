// Hand-maintained English->Tamil dictionary for every static UI label,
// heading, button, nav item, and other fixed chrome string in the app.
// Looked up synchronously by useStaticText/<S> — no IndicTrans2 call, no
// network round-trip, so toggling "View in Tamil" repaints these instantly.
// IndicTrans2 (via <T>/useTranslatedText) is reserved for dynamic
// AI-generated content (chat answers, clause explanations, summaries, risk
// recommendations, authenticity/contradiction explanations, original clause
// translation) that can't be enumerated ahead of time.
//
// Keys must match the exact English string passed to <S>/useStaticText,
// including punctuation and trailing colons/spaces. Finite-vocabulary
// values (risk levels, severities, badge text, etc.) are included as their
// exact rendered form (e.g. the .toUpperCase() + " RISK" combination),
// since those are still a fixed, enumerable set, not free-form AI text.
export const STATIC_STRINGS_TA: Record<string, string> = {
  // Navigation
  Dashboard: "டாஷ்போர்டு",
  "Clause Analysis": "விதிமுறை பகுப்பாய்வு",
  "Risk Analysis": "இடர் பகுப்பாய்வு",
  "Contradiction Detection": "முரண்பாடு கண்டறிதல்",
  "Comparison Center": "ஒப்பீட்டு மையம்",
  Tamil: "தமிழ்",
  "View in Tamil": "தமிழில் காண்க",

  // Sidebar / account
  "Legal Intelligence Platform": "சட்ட நுண்ணறிவு தளம்",
  "Log Out": "வெளியேறு",
  "Delete Account": "கணக்கை நீக்கு",
  "Delete your account?": "உங்கள் கணக்கை நீக்கவா?",
  "This permanently deletes your account, every document you've uploaded, and all associated analysis data. This cannot be undone.":
    "இது உங்கள் கணக்கு, நீங்கள் பதிவேற்றிய ஒவ்வொரு ஆவணம் மற்றும் தொடர்புடைய அனைத்து பகுப்பாய்வு தரவையும் நிரந்தரமாக நீக்கிவிடும். இதை மீட்டெடுக்க முடியாது.",
  "Confirm your password": "உங்கள் கடவுச்சொல்லை உறுதிப்படுத்தவும்",
  Cancel: "ரத்துசெய்",
  "Delete My Account": "என் கணக்கை நீக்கு",
  "Document Management": "ஆவண மேலாண்மை",
  "Your documents": "உங்கள் ஆவணங்கள்",
  "Failed to load documents.": "ஆவணங்களை ஏற்ற முடியவில்லை.",
  "No documents yet.": "இதுவரை ஆவணங்கள் இல்லை.",
  Active: "செயலில்",
  "Set Active": "செயல்படுத்து",
  Delete: "நீக்கு",
  processing: "செயலாக்கத்தில்",
  processed: "செயலாக்கப்பட்டது",
  failed: "தோல்வியடைந்தது",

  // Upload panel
  "Upload a document": "ஆவணத்தை பதிவேற்று",
  "PDF, Word, or text contracts. Images are OCR'd automatically before analysis.":
    "PDF, Word, அல்லது உரை ஒப்பந்தங்கள். படங்கள் பகுப்பாய்வுக்கு முன் தானாக OCR செய்யப்படும்.",
  "This document has already been analyzed.": "இந்த ஆவணம் ஏற்கனவே பகுப்பாய்வு செய்யப்பட்டுள்ளது.",
  "Process Document": "ஆவணத்தை செயலாக்கு",
  "Processing Status: running multi-agent analysis…": "செயலாக்க நிலை: பல்-முகவர் பகுப்பாய்வு நடைபெறுகிறது…",
  "uploaded.": "பதிவேற்றப்பட்டது.",
  "clauses found.": "விதிமுறைகள் கண்டறியப்பட்டன.",
  Risk: "இடர்",

  // Page headers (titles/subtitles/badges)
  "Platform Dashboard": "தளத்தின் டாஷ்போர்டு",
  "Next-generation AI legal intelligence platform": "அடுத்த தலைமுறை AI சட்ட நுண்ணறிவு தளம்",
  Overview: "மேலோட்டம்",
  "Detailed clause-level analysis of the active document": "செயலில் உள்ள ஆவணத்தின் விதிமுறை அடிப்படையிலான விரிவான பகுப்பாய்வு",
  "Risk Analysis & Mitigation Advisor": "இடர் பகுப்பாய்வு மற்றும் தணிப்பு ஆலோசகர்",
  "A plain-English breakdown of document-wide risk and authenticity, plus every flagged clause explained.":
    "ஆவணம் முழுவதற்குமான இடர் மற்றும் நம்பகத்தன்மையை எளிய ஆங்கிலத்தில் விளக்கும் பகுப்பாய்வு, மேலும் கொடி காட்டப்பட்ட ஒவ்வொரு விதிமுறையும் விளக்கப்படுகிறது.",
  "Contradiction & Inconsistency Finder": "முரண்பாடு மற்றும் முரண்பாடின்மை கண்டறிபவர்",
  "Identifies conflicting statements, inconsistent obligations, and contradictory terms within the document.":
    "ஆவணத்திற்குள் முரண்படும் அறிக்கைகள், முரண்பட்ட கடமைகள் மற்றும் முரண்பட்ட விதிமுறைகளை கண்டறிகிறது.",
  "Select two agreements to analyze structural differences, clause variations, and potential vulnerabilities between them. This module keeps its own document selection and never changes your globally active document.":
    "இரண்டு ஆவணங்களுக்கு இடையேயான கட்டமைப்பு வேறுபாடுகள், விதிமுறை மாறுபாடுகள் மற்றும் சாத்தியமான பாதிப்புகளை பகுப்பாய்வு செய்ய இரண்டு ஒப்பந்தங்களைத் தேர்ந்தெடுக்கவும். இந்த பிரிவு அதன் சொந்த ஆவணத் தேர்வை வைத்திருக்கும், உங்கள் உலகளாவிய செயலில் உள்ள ஆவணத்தை மாற்றாது.",
  "No active document": "செயலில் உள்ள ஆவணம் இல்லை",

  // Comparison page
  "Please upload at least two documents to use Comparison Center.": "ஒப்பீட்டு மையத்தைப் பயன்படுத்த குறைந்தது இரண்டு ஆவணங்களையாவது பதிவேற்றவும்.",
  "Which documents would you like to compare?": "எந்த ஆவணங்களை ஒப்பிட விரும்புகிறீர்கள்?",
  "Document 1:": "ஆவணம் 1:",
  "Document 2:": "ஆவணம் 2:",
  "Please select two different documents to compare.": "ஒப்பிட இரண்டு வெவ்வேறு ஆவணங்களைத் தேர்ந்தெடுக்கவும்.",
  "Compare Documents": "ஆவணங்களை ஒப்பிடு",
  "Failed to compile comparison:": "ஒப்பீட்டைத் தொகுக்க முடியவில்லை:",
  "Change Summary": "மாற்றச் சுருக்கம்",
  "Added Clauses": "சேர்க்கப்பட்ட விதிமுறைகள்",
  "Removed Clauses": "நீக்கப்பட்ட விதிமுறைகள்",
  "Modified Clauses": "மாற்றப்பட்ட விதிமுறைகள்",
  "Risk Changes": "இடர் மாற்றங்கள்",
  "Detailed Difference Report": "விரிவான வேறுபாடு அறிக்கை",
  "Side-by-Side Reference": "இணை ஒப்பீட்டு குறிப்பு",
  "Type:": "வகை:",
  "Document 1": "ஆவணம் 1",
  "Document 2": "ஆவணம் 2",
  "*(Clause not present in Agreement A)*": "*(இந்த விதிமுறை ஒப்பந்தம் A-வில் இல்லை)*",
  "*(Clause not present in Agreement B)*": "*(இந்த விதிமுறை ஒப்பந்தம் B-வில் இல்லை)*",
  "Similarity Score": "ஒற்றுமை மதிப்பெண்",

  // Contradiction page / card
  "Please select an active document in the sidebar to review contradictions.":
    "முரண்பாடுகளை மதிப்பாய்வு செய்ய பக்கப்பட்டியில் ஒரு செயலில் உள்ள ஆவணத்தைத் தேர்ந்தெடுக்கவும்.",
  "Finding contradictions and inconsistencies in this document… This may take a few seconds, depending on the document's length and complexity.":
    "இந்த ஆவணத்தில் முரண்பாடுகள் மற்றும் முரண்பாடின்மைகளைக் கண்டறிகிறது… ஆவணத்தின் நீளம் மற்றும் சிக்கலைப் பொறுத்து இதற்கு சில வினாடிகள் ஆகலாம்.",
  "Failed to load contradictions for this document.": "இந்த ஆவணத்திற்கான முரண்பாடுகளை ஏற்ற முடியவில்லை.",
  Found: "கண்டறியப்பட்டது",
  "internal conflicts:": "உள் முரண்பாடுகள்:",
  "No conflicting clauses or internal contradictions were detected in this agreement!":
    "இந்த ஒப்பந்தத்தில் முரண்படும் விதிமுறைகள் அல்லது உள் முரண்பாடுகள் எதுவும் கண்டறியப்படவில்லை!",
  "Re-analyze with AI": "AI மூலம் மீண்டும் பகுப்பாய்வு செய்",
  "Failed to re-analyze this document.": "இந்த ஆவணத்தை மீண்டும் பகுப்பாய்வு செய்ய முடியவில்லை.",
  clauses: "விதிமுறைகள்",
  "Affected Clauses": "பாதிக்கப்பட்ட விதிமுறைகள்",
  "Explanation of Conflict:": "முரண்பாட்டின் விளக்கம்:",
  "Suggested Resolution": "பரிந்துரைக்கப்பட்ட தீர்வு",
  "HIGH Severity": "உயர் தீவிரம்",
  "MEDIUM Severity": "நடுத்தர தீவிரம்",
  "LOW Severity": "குறைந்த தீவிரம்",
  "HIGH SEVERITY": "உயர் தீவிரம்",
  "MEDIUM SEVERITY": "நடுத்தர தீவிரம்",
  "LOW SEVERITY": "குறைந்த தீவிரம்",

  // Clause analysis page
  "Please select an active document in the sidebar or upload one to begin.":
    "தொடங்க பக்கப்பட்டியில் ஒரு செயலில் உள்ள ஆவணத்தைத் தேர்ந்தெடுக்கவும் அல்லது ஒன்றைப் பதிவேற்றவும்.",
  "Failed to load clauses for this document.": "இந்த ஆவணத்திற்கான விதிமுறைகளை ஏற்ற முடியவில்லை.",
  "No clauses parsed for this document.": "இந்த ஆவணத்திற்கு விதிமுறைகள் எதுவும் பகுப்பாய்வு செய்யப்படவில்லை.",
  "Clause Type": "விதிமுறை வகை",
  "Risk Level": "இடர் நிலை",
  "Importance Level": "முக்கியத்துவ நிலை",
  All: "அனைத்தும்",
  High: "உயர்",
  Medium: "நடுத்தரம்",
  Low: "குறைவு",
  None: "இல்லை",
  Critical: "மிக முக்கியமானது",
  Important: "முக்கியமானது",
  Informational: "தகவல் சார்ந்தது",
  "Back to Clauses": "விதிமுறைகளுக்குத் திரும்பு",
  "View Structured Fields": "கட்டமைக்கப்பட்ட புலங்களைக் காண்க",
  "Search field label or value": "புலப் பெயர் அல்லது மதிப்பைத் தேடு",
  "Search title or text": "தலைப்பு அல்லது உரையைத் தேடு",
  "e.g. termination, liability…": "எ.கா. முடிவு, பொறுப்பு…",
  Showing: "காட்டுகிறது",
  of: "இல்",
  "structured field(s) — policy/metadata values, not legal clauses:":
    "கட்டமைக்கப்பட்ட புலங்கள் — பாலிசி/மேலதிக தரவு மதிப்புகள், சட்ட விதிமுறைகள் அல்ல:",
  "No structured fields match your search.": "உங்கள் தேடலுக்கு பொருந்தும் கட்டமைக்கப்பட்ட புலங்கள் இல்லை.",
  "clauses:": "விதிமுறைகள்:",
  "No value extracted.": "மதிப்பு எதுவும் பிரித்தெடுக்கப்படவில்லை.",

  // Risk analysis page
  "Please select an active document in the sidebar to review risks.":
    "இடர்களை மதிப்பாய்வு செய்ய பக்கப்பட்டியில் ஒரு செயலில் உள்ள ஆவணத்தைத் தேர்ந்தெடுக்கவும்.",
  "Risk Overview": "இடர் மேலோட்டம்",
  "Recompute Authenticity": "நம்பகத்தன்மையை மீண்டும் கணக்கிடு",
  "Failed to recompute authenticity.": "நம்பகத்தன்மையை மீண்டும் கணக்கிட முடியவில்லை.",
  Hide: "மறை",
  "Authenticity Factor Breakdown": "நம்பகத்தன்மை காரணி விவரம்",
  "Document Risk": "ஆவண இடர்",
  "Quick Estimate": "விரைவு மதிப்பீடு",
  "Failed to generate document risk score.": "ஆவண இடர் மதிப்பெண்ணை உருவாக்க முடியவில்லை.",
  Recommendations: "பரிந்துரைகள்",
  "Excellent! No High or Medium risk clauses were detected in this agreement.":
    "சிறப்பு! இந்த ஒப்பந்தத்தில் உயர் அல்லது நடுத்தர இடர் விதிமுறைகள் எதுவும் கண்டறியப்படவில்லை.",
  Category: "வகை",
  "All Categories": "அனைத்து வகைகளும்",
  "All Levels": "அனைத்து நிலைகளும்",
  "No flagged clauses match the selected filters.": "தேர்ந்தெடுக்கப்பட்ட வடிகட்டிகளுக்கு பொருந்தும் கொடியிடப்பட்ட விதிமுறைகள் இல்லை.",
  "Flagged Clauses": "கொடியிடப்பட்ட விதிமுறைகள்",
  "High Risk": "உயர் இடர்",
  "Medium Risk": "நடுத்தர இடர்",
  "Authenticity Score": "நம்பகத்தன்மை மதிப்பெண்",
  "HIGHLY AUTHENTIC": "மிகவும் நம்பகமானது",
  "STRONGLY AUTHENTIC": "வலுவாக நம்பகமானது",
  "LIKELY AUTHENTIC": "நம்பகமானதாக இருக்கலாம்",
  "MOSTLY AUTHENTIC": "பெரும்பாலும் நம்பகமானது",
  SUSPICIOUS: "சந்தேகத்திற்குரியது",
  "LIKELY MANIPULATED OR FORGED": "கையாளப்பட்டது அல்லது போலியானது என சந்தேகிக்கப்படுகிறது",
  "INSUFFICIENT SIGNAL": "போதுமான தரவு இல்லை",
  HIGH: "உயர்",
  MEDIUM: "நடுத்தரம்",
  LOW: "குறைவு",
  NONE: "இல்லை",

  // Dashboard page
  "Please select an active document in the sidebar to view its dashboard metrics.":
    "அதன் டாஷ்போர்டு அளவீடுகளைக் காண பக்கப்பட்டியில் ஒரு செயலில் உள்ள ஆவணத்தைத் தேர்ந்தெடுக்கவும்.",
  "Failed to load dashboard metrics for this document.": "இந்த ஆவணத்திற்கான டாஷ்போர்டு அளவீடுகளை ஏற்ற முடியவில்லை.",
  "Upload and parse a document to view risk distributions.": "இடர் பரவல்களைக் காண ஒரு ஆவணத்தைப் பதிவேற்றி பகுப்பாய்வு செய்யவும்.",
  "Total Clauses": "மொத்த விதிமுறைகள்",
  "Risky Clauses (High/Med)": "இடர் விதிமுறைகள் (உயர்/நடுத்தரம்)",
  Contradictions: "முரண்பாடுகள்",
  "Document Type": "ஆவண வகை",
  "Risk:": "இடர்:",
  clause: "விதிமுறை",
  "Avg Importance": "சராசரி முக்கியத்துவம்",
  "High Risk Clauses": "உயர் இடர் விதிமுறைகள்",

  // ClauseCard
  "Clause Title": "விதிமுறைத் தலைப்பு",
  Type: "வகை",
  Unclassified: "வகைப்படுத்தப்படவில்லை",
  "Clause Classification": "விதிமுறை வகைப்பாடு",
  "Compliance Status": "இணக்க நிலை",
  "Original Clause Text": "மூல விதிமுறை உரை",
  "English Original": "ஆங்கில மூலம்",
  "Tamil Translation": "தமிழ் மொழிபெயர்ப்பு",
  "Simplify Clause": "விதிமுறையை எளிதாக்கு",
  "Generating plain-English redraft...": "எளிய ஆங்கில மறுவரைவை உருவாக்குகிறது...",
  "Simplification failed.": "எளிமையாக்கம் தோல்வியடைந்தது.",
  "AI generation failed — showing the previously saved plain-English redraft instead.":
    "AI உருவாக்கம் தோல்வியடைந்தது — முன்பு சேமிக்கப்பட்ட எளிய ஆங்கில மறுவரைவு காட்டப்படுகிறது.",
  "Impact Analysis": "தாக்க பகுப்பாய்வு",
  "Impact scoring unavailable for this clause.": "இந்த விதிமுறைக்கு தாக்க மதிப்பெண் கிடைக்கவில்லை.",
  "Impact Level:": "தாக்க நிலை:",
  "Overall severity of this clause's impact across legal, financial, business, and compliance dimensions.":
    "சட்டம், நிதி, வணிகம் மற்றும் இணக்கம் ஆகிய பரிமாணங்களில் இந்த விதிமுறையின் தாக்கத்தின் ஒட்டுமொத்த தீவிரம்.",
  "Business Impact:": "வணிகத் தாக்கம்:",
  "How significantly this clause could affect business operations, SLAs, or deliverables.":
    "இந்த விதிமுறை வணிக செயல்பாடுகள், SLA-க்கள் அல்லது ஒப்படைப்புகளை எந்த அளவிற்கு பாதிக்கக்கூடும் என்பது.",
  "Legal Impact:": "சட்டத் தாக்கம்:",
  "How significantly this clause could affect legal exposure or enforceability.":
    "இந்த விதிமுறை சட்ட ரீதியான வெளிப்பாடு அல்லது அமலாக்கத்தன்மையை எந்த அளவிற்கு பாதிக்கக்கூடும் என்பது.",
  "Regenerate with AI (Agent 7)": "AI மூலம் (Agent 7) மீண்டும் உருவாக்கு",
  CRITICAL: "மிக முக்கியமானது",
  IMPORTANT: "முக்கியமானது",
  INFORMATIONAL: "தகவல் சார்ந்தது",
  "HIGH RISK": "உயர் இடர்",
  "MEDIUM RISK": "நடுத்தர இடர்",
  "LOW RISK": "குறைந்த இடர்",
  "NONE RISK": "இடர் இல்லை",
  UNKNOWN: "தெரியவில்லை",
  "NEEDS REVIEW": "மறு ஆய்வு தேவை",
  MONITOR: "கண்காணிக்கவும்",
  COMPLIANT: "இணக்கமானது",

  // SimplifyResult headings
  "Plain English Explanation": "எளிய ஆங்கில விளக்கம்",
  "Easy Summary": "எளிய சுருக்கம்",
  Rights: "உரிமைகள்",
  Obligations: "கடமைகள்",
  "Hidden Risks": "மறைந்துள்ள இடர்கள்",
  "AI Recommendation": "AI பரிந்துரை",

  // FlaggedClauseCard
  Confidence: "நம்பகத்தன்மை",
  Importance: "முக்கியத்துவம்",
  "No text extracted for this clause.": "இந்த விதிமுறைக்கு உரை எதுவும் பிரித்தெடுக்கப்படவில்லை.",
  "View Full Clause": "முழு விதிமுறையையும் காண்க",
  "Hide Full Clause": "முழு விதிமுறையையும் மறை",
  "Why This Clause Is Risky": "இந்த விதிமுறை ஏன் இடர் நிறைந்தது",
  "No explanation recorded for this clause yet.": "இந்த விதிமுறைக்கு இதுவரை விளக்கம் எதுவும் பதிவு செய்யப்படவில்லை.",

  // AuthenticityBreakdown
  "Detected type:": "கண்டறியப்பட்ட வகை:",
  "Overall confidence:": "ஒட்டுமொத்த நம்பகத்தன்மை:",
  confidence: "நம்பகத்தன்மை",
  "Not applicable to this document": "இந்த ஆவணத்திற்கு பொருந்தாது",
  weight: "எடை",
  "Document Structure": "ஆவண கட்டமைப்பு",
  "Mandatory Clauses": "கட்டாய விதிமுறைகள்",
  "Cross-Field Consistency": "குறுக்கு-புல நிலைத்தன்மை",
  "Entity Verification": "நிறுவன சரிபார்ப்பு",
  "Digital Verification": "டிஜிட்டல் சரிபார்ப்பு",
  "Metadata Validation": "மேலதிகத் தரவு சரிபார்ப்பு",
  "Semantic Consistency": "சொற்பொருள் நிலைத்தன்மை",
  "Document-Type Checks": "ஆவண-வகை சரிபார்ப்புகள்",

  // ChatPanel / ChatBubble
  "Legal AI Assistant": "சட்ட AI உதவியாளர்",
  "Answer using:": "இதைப் பயன்படுத்தி பதிலளி:",
  Doc: "ஆவணம்",
  "Scope: active document": "வரம்பு: செயலில் உள்ள ஆவணம்",
  "Scope: entire workspace": "வரம்பு: முழு பணியிடமும்",
  "Scope:": "வரம்பு:",
  "compared document": "ஒப்பிடப்பட்ட ஆவணம்",
  "Clear Chat": "அரட்டையை அழி",
  Minimize: "சிறிதாக்கு",
  "Suggested questions:": "பரிந்துரைக்கப்பட்ட கேள்விகள்:",
  "Legal AI is thinking… (this may take a few seconds)": "சட்ட AI யோசித்துக் கொண்டிருக்கிறது… (இதற்கு சில வினாடிகள் ஆகலாம்)",
  "Ask a legal question…": "ஒரு சட்டக் கேள்வியைக் கேளுங்கள்…",
  "What is the termination clause?": "காலவரையறை விதிமுறை என்ன?",
  "What are my obligations?": "எனது கடமைகள் என்னென்ன?",
  "Is there a liability cap?": "பொறுப்பு வரம்பு ஏதேனும் உள்ளதா?",
  Citations: "மேற்கோள்கள்",

  // HallucinationReport
  "Trust Score": "நம்பிக்கை மதிப்பெண்",
  "Hallucination Check": "மாயத்தோற்ற சரிபார்ப்பு",
  Hallucination: "மாயத்தோற்றம்",
  Groundedness: "ஆதார அடிப்படை",
  "Citation Quality": "மேற்கோள் தரம்",
  "Unsupported Claims": "ஆதரிக்கப்படாத கூற்றுகள்",
  "No unsupported claims detected.": "ஆதரிக்கப்படாத கூற்றுகள் எதுவும் கண்டறியப்படவில்லை.",
  "This answer may contain information not fully supported by the uploaded legal document.":
    "இந்த பதிலில் பதிவேற்றப்பட்ட சட்ட ஆவணத்தால் முழுமையாக ஆதரிக்கப்படாத தகவல்கள் இருக்கக்கூடும்.",
};
