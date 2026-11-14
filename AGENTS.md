Basic rules

- ask permission BEFORE editing any test files
- there is a precommit hook that runs tests and all tests MUST pass before you commit
- comments inline should balance succinct and informative, and ideally minimise the amount of lines they use
- rather than storing constants in modules, use the django settings module
- when constructing queries, consider the idiomatic approach of using managers rather than constructing the same queries over and over again.