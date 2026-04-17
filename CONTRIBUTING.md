# Contributing to Mylar

## Pull Requests
- Only make pull requests against the `nightly` branch - never `stable`!
- You're probably going to get some comments or questions from us.  They will be to ensure consistency and maintainability
- Each PR should come from its own feature branch not the nightly branch in your fork, with a meaningful name (what is being added/fixed).
- Make meaningful commits, squash them if necessary.
- Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) to format your commit messages - applications like [commitizen](https://commitizen-tools.github.io/commitizen/) can help you get in that habit.
- Try to keep it to one feature/bug fix per pull request to keep things clean and easy to understand.
- Ensure that you've enabled a docker image to be built on your own branch using our GitHub Actions workflows.
- Rebase before submitting PRs.  If the nightly branch has moved on since you started writing, don't expect reviewers to handle merging your code in case it conflicts.

## AI Contribution Policy
Our AI contribution policy is based on three core principles.

**DISCLOSURE**: We expect you to be up front about your usage of AI in changes.  If you've utilised it and stuck to the guidelines below, you should be able to justify why quite easily.

**ENGAGEMENT**: We expect you to engage with us about your changes, so that we can understand what you're changing and coordinate with any other ongoing work.  Hop into the discord and have a chat before you start working on a feature.

**UNDERSTANDING**: This is leaving the greatest until last.  We expect you to fully understand what you are submitting, and be able to explain the changes in your own words.  You must be leading the AI, not letting the AI lead you.  This includes understanding **why** the changes are being made.

### Guidelines
AI, in some measure, is likely to form a part of the workflow of most developers at this point.  We appreciate and understand this, but we still believe change needs to be driven by developers themselves, not by the AI.  It is there to act as an aid, and a labour saving device.

Ensure that you have read and understood every line of code that you are submitting, as well as the context of those lines of code.  Make sure that you have tested, not just for the scenario you are implementing, but also other scenarios that share that part of the codebase.  Don't test your code in isolation - it is expected that you have tested against real data in a running instance of Mylar.

Do not write your PRs using AI.  If you can't succinctly explain what you are changing, what problems you are solving, how you've tested, etc. then you are not the driver of change.  Nobody wants to read 5 pages of grandiose corporate waffle.

This policy, much like the AI space, will evolve over time.  While we currently have not put in place automated controls around PR submission to enforce these, we may deem these necessary over time.  The fewer bad experiences we have, the freer we are likely to keep the process.  Don't be the person that makes things worse.

