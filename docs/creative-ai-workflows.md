# Creative AI Workflows: Generative Visual & Audio Art

This document catalogs state-of-the-art open-source methods, tools, and frameworks for automated digital art, music, and creative content generation. It provides guidance for integrating reproducible, extensible creative pipelines into the Local Agent Substrate.

## Overview

The landscape of open-source creative AI has matured significantly, with production-grade tools for image generation, video synthesis, audio/music creation, and automated workflow orchestration. This document focuses on **trustworthy, open-source projects** that prioritize reproducibility, local execution, and community-driven innovation.

## Key Principles

- **Reproducibility**: Deterministic workflows with versioned models and cached results
- **Local-First**: Self-hosted execution with optional cloud APIs for closed models
- **Extensibility**: Node-based architectures that allow custom model integration
- **Open Source**: MIT/Apache/GPL licensed projects with active communities
- **Composability**: Tools that can be chained into automated pipelines

---

## Visual Art Generation

### Node-Based Workflow Engines

#### 1. **ComfyUI** (Industry Standard)
- **Type**: Node-based GUI for image/video generation
- **License**: Open source (GPL)
- **Key Features**:
  - Modular node system for chaining models
  - Supports Stable Diffusion, LoRA, ControlNet
  - Custom node extension system
  - Workflow serialization (JSON)
- **Use Case**: Primary generation engine for complex pipelines
- **Integration**: Can be embedded via API or run as standalone service
- **Repository**: https://github.com/comfyanonymous/ComfyUI

#### 2. **Inline Studio**
- **Type**: AI filmmaking node canvas
- **License**: GPL-3.0
- **Key Features**:
  - End-to-end video pipeline from moodboard to final cut
  - Local diffusion engine (Inline Core) + hosted fal models
  - Versioned, non-destructive takes
  - LoRA training on the canvas
  - Frame-to-frame chaining
- **Unique**: Single-process architecture (Python backend + web UI)
- **Repository**: https://github.com/inlineresearch/Inline-Studio

#### 3. **Nebula Nodes**
- **Type**: Multi-surface AI creation studio
- **License**: MIT
- **Key Features**:
  - 142 built-in nodes across 15 provider families
  - Universal nodes (OpenRouter, Nous, Replicate, FAL) reaching 300+ models
  - Smart subgraph caching (skips unchanged nodes)
  - Real-time streaming outputs
  - Agent chat (Daedalus/Claude/Codex) builds graphs from natural language
  - Seven workspaces: Canvas, Create, Cinema, Character, Moodboard, Video Editor
- **Architecture**: FastAPI backend + React frontend + WebSocket streaming
- **Repository**: https://github.com/JustinPerea/nebula-nodes

#### 4. **Vibe Workflow**
- **Type**: Open-source alternative to Weavy AI/Krea Nodes
- **License**: MIT
- **Key Features**:
  - Node-based AI workflow builder
  - Self-hostable with MuAPI integration
  - Extensible architecture for custom AI nodes
  - No vendor lock-in
- **Repository**: https://github.com/SamurAIGPT/Vibe-Workflow

#### 5. **Graphix**
- **Type**: AI-native graphic novel/comic creation
- **License**: Custom (NOASSERTION)
- **Key Features**:
  - Story-first workflow (premise → beats → panels)
  - Character consistency via IP-Adapter embeddings
  - Narrative context flows into generation prompts
  - Rapid prototyping and moodboards
- **Repository**: https://github.com/peleke/graphix

### Foundation Models

#### Image Generation
- **Stable Diffusion XL (SDXL)**: 1024×1024 high-quality generation
- **Flux.1**: State-of-the-art text-to-image (black-forest-labs)
- **Krea 2**: 12.9B single-stream MMDiT (RAW + Turbo variants)
- **Z-Image**: Turbo variant optimized for speed
- **Ideogram v3**: Advanced text rendering capabilities

#### Model Hosting/API
- **fal.ai**: Hosted closed models (GPT-2 Image, Nano Banana, Seedance)
- **Replicate**: API access to various models
- **RunPod**: Cloud GPU hosting for self-hosted ComfyUI

---

## Audio & Music Generation

### Open-Source Music Models

#### 1. **MusicGen (Meta/AudioCraft)**
- **License**: MIT (code), CC-BY-NC 4.0 (weights)
- **Type**: Autoregressive LM over compressed audio tokens
- **Key Features**:
  - Text-to-music and melody-guided generation
  - Multiple sizes: 300M, 1.5B, 3.3B parameters
  - Stereo models available
  - 30-second clips (base), extendable
- **Repository**: https://github.com/facebookresearch/audiocraft
- **Use Case**: Research and prototyping, short-form music

#### 2. **Stable Audio 3.0 (Stability AI)**
- **License**: Open-weights (CC-BY for small/medium)
- **Type**: Latent diffusion model
- **Key Features**:
  - **Variable-length generation** (up to 6+ minutes)
  - 4096× downsampling (efficient)
  - Inpainting (edit segments, extend)
  - Full song composition on-device (3.0 Small)
  - Licensed training data
  - Fast inference (<2s on H200)
- **Models**: Small SFX, Small, Medium (open), Large (API)
- **Repository**: https://github.com/Stability-AI/stable-audio-tools
- **Advantage**: Only open model supporting long-form structured music

#### 3. **SongGeneration (Tencent)**
- **License**: Custom (check repository)
- **Type**: Hybrid LLM-Diffusion
- **Key Features**:
  - **Commercial-grade** quality
  - Full songs with vocals (4m30s)
  - Multi-lingual lyrics (zh, en, es, ja, etc.)
  - Reference audio conditioning
  - 4B parameter model
  - LeVo 2 architecture (Hierarchical LM + Diffusion)
- **Performance**: PER 8.55%, rivals closed models
- **Repository**: https://github.com/tencent-ailab/SongGeneration
- **Use Case**: Production music with vocals

#### 4. **HeartMuLa**
- **License**: Apache 2.0
- **Type**: Music foundation model family
- **Key Features**:
  - HeartMuLa-7B (comparable to Suno)
  - HeartCodec: 12.5 Hz music codec
  - HeartTranscriptor: Lyrics transcription
  - HeartCLAP: Audio-text alignment
  - Multilingual support
  - Lyrics and tags conditioning
- **Repository**: https://github.com/HeartMuLa/HeartMuLa
- **Status**: Internal version comparable to Suno

#### 5. **TangoFlux**
- **License**: Stability AI Community License (non-commercial research)
- **Type**: Super fast text-to-audio with flow matching
- **Key Features**:
  - 30-second stereo audio at 44.1kHz
  - ~3 seconds generation on A40 GPU
  - FluxTransformer architecture
  - Preference optimization (CRPO dataset)
- **Repository**: https://github.com/declare-lab/TangoFlux

#### 6. **MOSS-TTS (OpenMOSS)**
- **License**: Apache 2.0
- **Type**: Speech and sound generation
- **Key Features**:
  - 4B parameter local transformer (48kHz stereo)
  - MOSS-Audio-Tokenizer-v2
  - Voice cloning, style control
  - Sound effects generation
  - Real-time streaming
- **Repository**: https://github.com/OpenMOSS/MOSS-TTS

### Audio Toolkits

#### AudioCraft (Meta)
- Comprehensive toolkit for audio generation
- Includes: MusicGen, AudioGen, EnCodec, MAGNeT, JASCO
- Training and inference code
- Installation: `pip install audiocraft`

---

## Automated Creative Workflows

### Agentic Orchestration

#### 1. **Open Lovart (Open AI Design Agent)**
- **Type**: Autonomous multi-step creative agent
- **License**: MIT
- **Key Features**:
  - Natural language brief → full creative deliverable
  - Orchestrates 200+ image/video models
  - Brand kit conditioning (palette, fonts, logo)
  - Multi-image reference (up to 14)
  - Workflow Studio (node-based pipeline builder)
  - Inspectable agent loop
- **Models**: Flux 2 Pro, Nano Banana 2, Ideogram v3, Recraft v3, Kling, Sora, Veo, Runway
- **Repository**: https://github.com/framefutura/Open-AI-Design-Agent

#### 2. **Vibe AIGC**
- **Type**: Agentic content generation framework
- **License**: MIT
- **Key Features**:
  - Decomposes "Vibes" into executable DAG workflows
  - MetaPlanner + KnowledgeBase + ToolRegistry
  - Parallel execution of independent nodes
  - Checkpoint/resume for long workflows
  - ComfyUI integration
  - Vision-language model feedback
- **Based on**: arXiv:2602.04575
- **Repository**: https://github.com/jmanhype/vibe-aigc

#### 3. **PipelineKit**
- **Type**: AI-orchestrated Blender production
- **License**: Custom
- **Key Features**:
  - Typed Blender operations (8 first-class ops)
  - LLM-planned DAG execution
  - Multi-lane orchestration (Groq, OpenRouter, Codex)
  - Approval gating
  - Live scene state polling
- **Repository**: https://github.com/pradhankukiran/pipeline-kit

#### 4. **OpenMontage**
- **Type**: Agentic video production system
- **License**: AGPL-3.0
- **Key Features**:
  - 11 production pipelines
  - 49 tools, 400+ agent skills
  - Scored provider selection (7 dimensions)
  - Decision audit trail
  - Quality gates (ffprobe, frame sampling, audio analysis)
  - No vendor lock-in
- **Architecture**: Agent-first (your AI coding assistant is the orchestrator)
- **Repository**: https://github.com/iRaees/OpenMontage

---

## Integration Patterns

### 1. Cache-Aware Creative Workflows

The substrate's `TaskCache` and `CacheStore` integrate naturally with creative AI workflows:

```python
from substrate.cache_store import CacheStore
from substrate.task_cache import TaskCache

# Initialize cache
store = CacheStore("state/cache")
task_cache = TaskCache(store)

# Cache AI image generation calls
def generate_image(prompt: str) -> str:
    # Call ComfyUI, fal.ai, or other service
    return image_url

result, meta = task_cache.cached_invoke(
    "fal", "gpt2-image", prompt, generate_image,
    tags={"image", "generative"}
)

# Decompose complex creative objectives
report = task_cache.run_cached_subtasks(
    objective="Create brand identity package",
    context="Modern tech startup, blue/white palette",
    runner=generate_image,
    provider="fal",
    model="gpt2-image"
)
```

### 2. Node-Based Pipeline Integration

Substrate can orchestrate node-based creative tools:

- **ComfyUI**: REST API or file-based workflow triggers
- **Inline Studio**: Single-process Python backend integration
- **Nebula Nodes**: FastAPI backend with WebSocket streaming
- **Custom Nodes**: Extend with substrate's provider system

### 3. Audio/Video Pipeline Example

```python
# Generate music with Stable Audio 3.0
# Generate voiceover with MOSS-TTS
# Combine with video generation (Runway, Luma)
# All cached by substrate's TaskCache
```

---

## Reproducibility Guidelines

### Model Versioning
- Pin model versions (e.g., `flux.1-dev`, `musicgen-stereo-large`)
- Use model cards for metadata
- Store generation parameters (seed, cfg_scale, steps)

### Deterministic Workflows
- Cache keys from `(kind, inputs)` SHA-256 hashes
- Subtask decomposition for complex objectives
- Versioned project exports (Inline Studio style)

### Quality Assurance
- Validation gates (like OpenMontage)
- Automated testing of generation outputs
- Human-in-the-loop approval for critical outputs

---

## Recommended Stack

### For Visual Art
1. **Primary**: ComfyUI (flexibility) or Inline Studio (video)
2. **Orchestration**: Nebula Nodes (multi-provider) or Vibe Workflow
3. **Models**: Flux.1, SDXL, Krea 2
4. **Caching**: Substrate TaskCache

### For Audio/Music
1. **Long-form Music**: Stable Audio 3.0 (open weights)
2. **Vocal Songs**: SongGeneration (Tencent)
3. **Short Clips**: MusicGen (Meta)
4. **Sound Effects**: AudioGen or MOSS-TTS

### For Automation
1. **Agentic**: Open Lovart (design) or Vibe AIGC (general)
2. **Video Production**: OpenMontage
3. **3D/Blender**: PipelineKit

---

## Open Challenges

1. **Consistent Character/Style**: Across multiple generations
2. **Long-Form Coherence**: Music structure, video narrative
3. **Real-Time Performance**: Low-latency generation
4. **Copyright/IP**: Training data provenance
5. **Evaluation Metrics**: Automated quality assessment

---

## References

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [Inline Studio](https://github.com/inlineresearch/Inline-Studio)
- [Nebula Nodes](https://github.com/JustinPerea/nebula-nodes)
- [Stable Audio 3.0](https://github.com/Stability-AI/stable-audio-tools)
- [SongGeneration](https://github.com/tencent-ailab/SongGeneration)
- [HeartMuLa](https://github.com/HeartMuLa/HeartMuLa)
- [Open Lovart](https://github.com/framefutura/Open-AI-Design-Agent)
- [Vibe AIGC](https://github.com/jmanhype/vibe-aigc)
- [AudioCraft](https://github.com/facebookresearch/audiocraft)
- [MOSS-TTS](https://github.com/OpenMOSS/MOSS-TTS)
