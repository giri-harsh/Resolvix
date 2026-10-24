---
queue: appointments
domain: nagar_sahayak
category: appointment_workflows
source_city: Bengaluru (RTOs and Passport Seva Kendras)
provenance: mixed
last_verified: 2026-08-23
---

# Appointment Workflows — RTO & Passport, Bengaluru

## RTO — driving licence test slot booking

Driving licence appointments in Karnataka (as in most states) are booked through the central **Sarathi** portal (sarathi.parivahan.gov.in), reached via the national Parivahan Sewa system. The process has two distinct appointment types, and citizens frequently confuse them:

1. **Learner's Licence (LL) test slot** — after submitting an LL application, if the state requires an in-person knowledge test rather than an online one, the applicant logs into Sarathi with their LL application number and date of birth, selects "LL Slot Booking," chooses their RTO from a list, and picks an available date from a calendar (available dates are typically shown in green).
2. **Permanent Driving Licence (DL) test slot** — this can only be booked **after holding the Learner's Licence for a minimum holding period (commonly cited as at least 30 days)** and submitting the permanent DL application. The same Sarathi login flow applies, using the DL application number instead. On the scheduled day, the applicant must bring the original Learner's Licence, the application form/slip, the appointment slip, the fee receipt, and (for the practical test) the vehicle's registration certificate, insurance, and pollution-under-control certificate.

Source: multiple independently published, cross-consistent guides describing the Sarathi/Parivahan slot-booking flow (cars24.com, itzeazy.in, vehicleinfo.app, and others), all describing the same underlying government portal mechanics.

**Practical citizen guidance worth including, disclosed as informal/anecdotal rather than official:** several of these guides note that Bengaluru RTO slots are frequently fully booked days in advance, and describe informal patterns (e.g., checking very early morning or late night) for catching newly released or cancelled slots. This is **not an official government-published release schedule** — the Sarathi portal does not publish a fixed slot-release time — and should be presented to a caller as informal, crowd-sourced advice, not as a guaranteed method, if raised at all.

Applicants are not restricted to their geographically nearest RTO; if a nearer RTO shows no availability, Sarathi allows booking at any RTO within the applicant's state. Rescheduling is generally permitted up to **two times** through the "Appointments" section before the scheduled date. If the driving test is passed, the physical licence is typically dispatched within **about 30 days** to the applicant's registered address.

## Passport Seva Kendra (PSK) — Bengaluru

Passport applications nationwide, including in Bengaluru, are processed exclusively through the **Passport Seva** online system (passportindia.gov.in / the Passport Seva Portal) — **walk-in applications are not accepted**; an online appointment at a Passport Seva Kendra (PSK) or Post Office PSK (POPSK) is mandatory. Bengaluru has multiple PSK locations, commonly cited as Lalbagh, Sai Arcade, and Koramangala. Source: multiple independently published guides describing the standard national PSK appointment workflow, cross-referenced for consistency, plus a Bengaluru-specific PSK location list.

**The booking sequence:** create an account on the Passport Seva Portal, select the application type (Fresh Passport, Re-issue/Renewal, or other services such as a Police Clearance Certificate), fill the form, pay the fee online, and only then book an appointment slot at a chosen PSK. The appointment confirmation generates an ARN (Application Reference Number), which the applicant must bring to the PSK along with original documents and self-attested photocopies for in-person verification and biometric capture.

**Fees** (for the standard, non-Tatkal scheme, as reported): **₹1,500** for a fresh or renewal 36-page booklet, and **₹2,000** for a 60-page booklet. An additional **₹2,000** Tatkal (urgent) surcharge applies on top of the base fee for expedited processing. **Processing time:** general (non-Tatkal) applications are reported to take roughly **30 to 45 days**; Tatkal applications are reported at roughly **7 to 14 days** by one source and "1 to 3 working days after document verification" by another — these figures are not fully consistent across sources and should be treated as an approximate range, not a guarantee, when speaking to a citizen. Source: multiple independently published passport-service guides (acko.com, passportsevain.com, and others).

Police verification is required for most fresh applications and is arranged separately after the PSK visit — this step is outside the applicant's direct control and is a common reason for delays beyond the general 30–45 day estimate. Application status can be tracked online using the ARN, or via SMS by texting `STATUS <15-digit application number>` to **9704100100**. The national Passport Seva Kendra call centre number is **1800-258-1800** (toll-free). Source: independently published passport-service guides, cross-referenced.

## What this category needs from the caller, structurally

Both of these workflows share a pattern worth encoding directly into the assistant's slot-filling logic: **an appointment cannot be booked until a prior application step is complete** (LL before DL; online form + payment before PSK appointment). A citizen who says "I want to book an appointment" for either service should first be asked whether they've already completed and paid for the underlying application — otherwise the assistant risks walking them toward a booking step they cannot actually complete yet.

## Sources

- sarathi.parivahan.gov.in and parivahan.gov.in (referenced via multiple independently published, cross-consistent user guides — first-party portal content was not directly fetched in this research session)
- passportindia.gov.in / Passport Seva Portal (referenced via multiple independently published guides describing PSK booking mechanics, Bengaluru PSK locations, fees, and processing times)
- **Recommended for direct verification before production use:** current fee schedule and processing-time figures on the live Passport Seva Portal and Sarathi portal, since both are subject to periodic government revision and this research relied on secondary citizen-guide sources rather than first-party fee notifications
