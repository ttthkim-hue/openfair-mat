# AI Usage & Transparency Disclosure (`OpenFAIR-Mat` v0.1.0)

This disclosure follows open-science software transparency best practices and **NLnet Foundation AI transparency guidelines**.

## 1. Software Engineering & Repository Code (`OpenFAIR-Mat`)
- **Runtime Guarantee (Zero AI Dependency):** The `openfair-mat` package (`src/openfair_mat/`) and `openfair-check` CLI execute **100% deterministically on CPU** using the Python standard library only. No LLM, generative AI model, neural network, or external paid API is called during dataset validation, SHA-256 hashing, or RO-Crate generation.
- **Development Assistance Disclosure:** During initial v0.1.0 scaffolding (unit structure, fixture generation, and test boilerplate), AI coding assistance was used under human specification and review. Every validation rule (crystallographic metric positivity, VASP 3x3 determinant volume, atom-count alignment, NaN/Inf parsing, unit-mixing checks, and RO-Crate 1.1 schema formatting) was verified directly via deterministic `pytest` unit/integration tests and CLI execution on valid and intentionally corrupted fixtures.

## 2. Data & IP Separation Statement
- Zero proprietary datasets, internal experimental logs, unpublished patents, or confidential work-product from any employer are included anywhere in this repository. All fixtures use public textbook reference materials (e.g., conventional diamond cubic Silicon, `Fd-3m`).
