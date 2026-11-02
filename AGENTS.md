# Project conventions

- Write engineering artifacts in English: identifiers, comments, docstrings, tests,
  README, architecture, technical explanations, notes, commits, and submissions.
- Use Conventional Commits with concise imperative subjects, such as `feat:`,
  `fix:`, `docs:`, `test:`, and `chore:`. Do not add assistant names, model names,
  or assistant co-author trailers to commit messages.
- Preserve original CSV values/columns and the original Portuguese policy document.
  Extracted policy headings and text stay Portuguese, with English metadata.
- Future customer-facing interactions use natural Brazilian Portuguese (pt-BR).
  Demonstration scenario titles, expected behavior, annotations, and explanations
  use English; translate important exchanges when evaluators need the context.
- Keep supplied materials, databases, derived policy text, detailed local notes,
  and credentials outside Git. Public fixtures must be explicitly synthetic.
- Keep authentication simulations in test support. Private repository access must
  remain denied by default until a trusted backend verifies identity.
- Run offline tests with `python -m unittest discover -s tests -v`; optional
  original-material checks require the explicit variables documented in README.
