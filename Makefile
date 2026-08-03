.PHONY: test lint test-signal test-mcp lint-signal lint-mcp

SIGNAL_DIR=services/radar-signal
MCP_DIR=services/btc-radar-mcp

test: test-signal test-mcp

lint: lint-signal lint-mcp

test-signal:
	$(MAKE) -C $(SIGNAL_DIR) test

test-mcp:
	$(MAKE) -C $(MCP_DIR) test

lint-signal:
	$(MAKE) -C $(SIGNAL_DIR) lint

lint-mcp:
	$(MAKE) -C $(MCP_DIR) lint

