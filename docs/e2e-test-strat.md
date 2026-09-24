## E2E Playright Strat

# Environments

I chose to have development, testing, and production environments so that we have a dedicated environment for running tests. This prevents us from cross pollinating the production database with test users created during E2E testing, as we are using the real database rather than mocking it.

# Mock LLM calls to get a search response & when creating embeddings using openAI embedding model

Mocking the LLM calls will make E2E tests run faster because we dont have to wait for a response from the provider, its more reliable as the server may be down blocking E2E tests, also a lot cheaper as we mocking the call.
