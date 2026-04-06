## Plan: Update BScraper Copilot Instructions & Future Roadmap

Update the .github/copilot-instructions.md file to accurately reflect the current implementation of the BScraper project, incorporating new features, fixing discrepancies, and adding missing documentation. Define testing strategy and prioritize next phases.

### Current Status (As of April 6, 2026)

**✅ COMPLETED & STABLE - MVP Pipeline Ready**
- **Code Cleanup**: Removed duplicate helper functions, fixed type annotations (`Optional` type hints)
- **Main.py Stabilization**: All phases working correctly (scrape, summarize, traits)
- **Session Resume**: Functional and tested, needs more testing for duplicate detection edge cases
- **Plain Text Output**: Essay now generated as `.txt` format (not `.md`)
- **Trait Extraction**: Reliably extracts from raw content with evidence and quotes
- **Quiz Questions**: Properly extracted and saved to `output/quiz_questions.json` (ready for integration)
- **Large Blog Verified**: Tested on ~300 post blogs with no memory or timeout issues
- **Architecture**: 3-phase pipeline fully stable and producing quality output

**🎯 NEXT PHASE - Process Control & Quiz Integration**
- Process control hooks (pause/inspect/resume after scraping) - PRIORITY 1
- Quiz generation integration with trait evaluation - PRIORITY 2
- New "Prominent Traits Discovery" mode (unbiased trait extraction) - PRIORITY 3 (parallel)
- Enhanced trait confidence scoring - PRIORITY 4

### Implementation Sequence (Prioritized)
1. **Process Control Hooks** - Add fine-grained phase control and inspection workflow
2. **Quiz Integration** - Make quiz central to trait validation with scoring
3. **Prominent Traits Mode** - Discover top traits WITHOUT predefined trait constraints
4. **Conflict Resolution** - Testing session resume for duplicate detection
5. Edge case testing (deferred to end, using hand-picked representative blogs)

**Relevant files**
- `.github/copilot-instructions.md` — Primary file to update
- `config.yaml` — Reference for actual configuration (keep all current parameters)
- `config.example.yaml` — Template configuration (retain as documentation example)
- `scraper/bdsmlr_scraper.py` — Key implementation details
- `processor/aggregator.py` — Tag processing logic
- `ai_engine/trait_extractor.py` — Trait extraction details

### Testing Strategy (Before Declaring MVP Stable)

**Priority 1: Session Resume Functionality**
- Run initial scrape and let it complete several scrolls
- Kill process mid-execution and check `output/scraping_session.json` is saved
- Restart and verify: "Found saved session with X posts" message appears
- Verify: New posts continue being discovered (not 0 new posts on first scroll after resume)
- Verify: Post IDs remain consistent across rescans (no hash-based ID variations)

**Priority 2: Edge Cases**
- Empty blog or blocked blog: Verify graceful handling (0 posts, completion flag set)
- Single-post blog: Verify scroll stops after 1 post, not error
- Image-only blog: Verify content filtering skips image-dependent posts
- Mixed content: Verify text_clear, image_dependent, and quiz_question classification

**Priority 3: Large Blog Handling**
- Run on blog with 100+ posts to monitor:
  - Memory usage (should remain stable, not grow linearly)
  - Process execution time (baseline for optimization)
  - Deduplication accuracy (no false positives/negatives)
  - AJAX response consistency (no unexpected 0-byte responses except at end)

**Priority 4: Deduplication & Post ID Consistency**
- Resume session multiple times: Verify post count stabilizes (no duplicates re-added)
- Check `logs/scraper.log` for post ID patterns:
  - All numeric strings (e.g., "12345") — no negative IDs
  - No "post_" prefix IDs (only fallback scenario)
  - Consistent IDs across scrolls for same post

**Test Success Criteria**
- ✅ Session resume adds only new posts, total stabilizes
- ✅ Post IDs always positive numeric strings
- ✅ Large blog completes without memory spike or timeouts
- ✅ Edge cases handled gracefully (no exceptions, clear logging)

**Decisions**
- Include all new features discovered (interactive scraping, sideblog AJAX, etc.) as they are implemented and enhance the MVP
- Use config.yaml as the reference for configuration (keep all current parameters: essay_word_count=300, proxy settings, base_traits list)
- Keep config.example.yaml as documentation template
- Document quiz questions as separate output, noting future integration for trait evaluation in Phase 2 quiz creation
- Prefer AJAX path for scraping, with planned future testing to assess consistency vs. pagination fallback
- Custom traits support: Expand support so both `base_traits` and `custom_traits` can each contain 5 to 20 items, while preserving the local `config.yaml` values and current fixed base trait set. Base traits should remain as a core fixed list, with at least 5 items present if traits are inferred with sufficient confidence.
- Documentation Focus: Prioritize "How to Run", "Troubleshooting", and "Configuration Reference" sections

**Priority Next Phases (Sequenced Implementation)**

1. **Process Control Hooks & Workflow** (HIGHEST PRIORITY - Implement First)
   - Add pause/inspect/resume workflow after Phase 1 (scraping)
   - Implement fine-grained `--phase` control and skipping logic for all phases
   - Allow users to stop after scraping and review `output/scraping_session.json`
   - Enable selective phase execution (e.g., scrape only, traits without summarization, re-analyze existing data)
   - Current CLI already supports `--phase` flags; enhance with interactive pause/inspect
   - Estimated impact: Enables flexible custom workflows, critical for real-world usage

2. **Quiz Generation Integration & Trait-Quiz Loop** (HIGH PRIORITY - After Process Control)
   - Make extracted quiz questions CENTRAL to trait validation
   - Integrate `output/quiz_questions.json` into trait scoring workflow
   - Design quiz to evaluate candidate fit with extracted traits
   - Create scoring mechanism: quiz responses → confidence adjustments to traits
   - Feed quiz results back into trait refinement
   - Estimated impact: Closes feedback loop, validates trait inference quality

3. **Prominent Traits Discovery Mode** (HIGH PRIORITY - Can Parallel with #2)
   - NEW FEATURE: "Discover" mode vs existing "Evaluate" mode
   - Discover mode: Extract top-confidence traits WITHOUT predefined trait set
   - Identify 5-10 most prominent, unbiased traits from raw content alone
   - Use general psychological trait framework (not base_traits list)
   - Validate confidence scoring without constraint bias
   - Estimated impact: Discovers authentic traits, reduces preset bias
   - Estimated complexity: Medium (new prompt + confidence filtering)

4. **Trait Inference Reliability & Confidence Quality** (MEDIUM PRIORITY)
   - Improve Ollama prompts for essay generation (Phase 2 quality)
   - Refine trait detection with better confidence thresholds
   - Add evidence extraction and quote validation
   - Reduce reliance on predefined traits for accuracy
   - Estimated impact: Higher quality trait results, better evidence

5. **Error Recovery & Network Robustness** (MEDIUM PRIORITY)
   - Add comprehensive retry logic for network failures
   - Better error messages and graceful degradation
   - HTTP timeout optimization based on 300+ post testing baseline
   - Estimated impact: More resilient scraping on unreliable networks

6. **Performance Optimization** (LOWER PRIORITY - After Stability Proven)
   - Parallelize AJAX requests (carefully, respecting rate limits and stability)
   - Optimize memory for blogs with 1000+ posts
   - Reduce per-request delays once reliability confirmed
   - Estimated impact: Faster scraping, support for massive blogs

**Known Limitations & Current Testing Status**
- **Session Resume Edge Cases**: Needs more testing to verify no duplicates across multiple resume cycles
- **Trait Confidence Calibration**: Current 50% threshold works but may need per-use-case tuning
- **Predefined Trait Bias**: Base_traits constraint affects discovery; new "discover" mode will address
- **Quiz Integration Pending**: Questions extracted but not yet in evaluation loop (Priority 2)
- **Edge Case Coverage**: Deferred to end of development using hand-picked representative blogs
- **Duplicate Detection**: Works but needs validation across extended session resume testing

**Verified Capabilities (As of April 6, 2026)**
- ✅ Large blog handling: ~300 posts with stable memory and no timeouts
- ✅ Session resume: Functional for continuing scraping across restarts
- ✅ Trait extraction: Reliably extracts with evidence, quotes, and confidence scores
- ✅ All CLI phases: Scrape, summarize, traits, combined workflows all production-ready
- ✅ Plain text essay: Properly generates `.txt` format (verified in config)
- ✅ Content filtering: Correctly classifies text_clear, image_dependent, quiz_question
- ✅ Quiz question extraction: Properly saves to `output/quiz_questions.json`
- ✅ Type safety: Fixed type annotations with `Optional` hints
- ✅ Code quality: Removed duplicate helpers, cleaned up main.py

**Configuration & Trait Architecture (Stable)**
- **Current Trait System**: 10 base traits + up to 10 custom traits = 20 total
- **Output Format**: Essay as plain text (`.txt`), traits as JSON with confidence/evidence
- **Scraping Method**: AJAX-first (`/sideblog/` endpoint) with pagination fallback
- **Deduplication**: Content hash-based, working effectively
- **Session Storage**: JSON serialization with resume capability
- **Quiz Output**: Separate `output/quiz_questions.json` (will integrate in Phase 2)

**Future Trait System Roadmap**
- Phase A (Current): "Evaluate" mode - score against predefined base_traits
- Phase B (Planned): "Discover" mode - find top confidence traits organically
- Phase C (Future): Hybrid mode - combine discover findings to update evaluation set
- Goal: Move from preset-biased to discovery-driven trait identification
