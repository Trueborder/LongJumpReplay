# LongJumpReplay legal and purchasing research

Checked 2026-10-07 against official sources. This is implementation guidance, not a legal opinion.

- [GDPR, Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj): transparency, lawful basis, data-subject rights, processor controls, security and breach duties.
- [ÚOOÚ cookie guidance](https://uoou.gov.cz/verejnost/qa-otazky-a-odpovedi/cookies): technical storage can be necessary; non-essential storage requires prior consent; Accept and Reject must be equally easy and withdrawal must be as easy as consent. The guidance also covers local storage and similar technologies.
- [ČOI internet purchases](https://coi.gov.cz/faq/a-nakup-pres-internet/): pre-contract seller/product/price/delivery/withdrawal/complaint information and durable-medium confirmation are required; immediate digital delivery needs separate express request and acknowledgement where it affects withdrawal.
- [ČOI payment button](https://coi.gov.cz/tlacitko/): the final control must make the payment obligation clear; “Objednávka zavazující k platbě” is used in the LJR checkout.
- [ČOI ADR](https://coi.gov.cz/pro-podnikatele/informace-pro-prodejce-zbozi-a-sluzeb/mimosoudni-reseni-spotrebitelskych-sporu-adr/): the seller should provide the Czech ADR subject and web information. The discontinued EU ODR platform is not linked.
- [EU Consumer Rights Directive](https://eur-lex.europa.eu/eli/dir/2011/83/oj/eng): Article 16(m) requires express consent to start digital performance during withdrawal period and acknowledgement of the resulting loss where the statutory exception applies, plus trader confirmation.
- [EU Accessibility Act](https://eur-lex.europa.eu/eli/dir/2019/882/oj/eng) and [Czech implementing law](https://e-sbirka.gov.cz/sb/2023/424): applicability to the actual seller, service and exemptions still needs legal confirmation; the LJR statement does not claim formal conformity.
- [EU VAT OSS](https://vat-one-stop-shop.ec.europa.eu/one-stop-shop_en): cross-border B2C VAT treatment, consumer location evidence and OSS obligations must be confirmed by the accountant; the checkout leaves the VAT wording as a placeholder until verified.
- [Stripe Checkout](https://docs.stripe.com/payments/checkout): Checkout is created server-side and entitlement is granted from verified webhook events, not the browser return URL.
- [Stripe dispute evidence](https://docs.stripe.com/disputes/visual-evidence): dispute records are retained as an auditable order state; evidence and response operation still require Stripe Dashboard configuration.

Open decisions remain listed in `LEGAL_DATA_NEEDED.md`. No seller identity, VAT status, retention period, age rule, transfer mechanism, support promise or withdrawal outcome was invented.
