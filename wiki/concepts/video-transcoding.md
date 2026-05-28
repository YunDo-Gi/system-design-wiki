---
type: concept
tags: [video, media, encoding, streaming]
sources: [ch14]
---

# Video Transcoding (Encoding)

## 한 줄 정의

원본 영상을 **여러 포맷·해상도·비트레이트로 변환**해 다양한 기기·대역폭에서 매끄럽게 재생되도록 만드는 과정. adaptive bitrate streaming(ABR)의 전제다 (ch14, p.228-229).

## 왜 필요한가

raw 영상을 그대로 서비스할 수 없는 세 가지 이유:

1. **크기**: HD 1시간(60fps)이 수백 GB → 저장·전송 비현실적. 코덱 압축 필수.
2. **호환성**: 기기·브라우저마다 지원 포맷이 다름 → 여러 포맷으로 인코딩.
3. **adaptive quality**: 대역폭 높은 사용자엔 고해상도, 낮은 사용자엔 저해상도. 모바일은 네트워크가 출렁여 **재생 중 화질 자동 전환**이 필요 → 미리 여러 비트레이트로 만들어 둠.

## 핵심 메커니즘

### Container + Codec

| 요소 | 역할 | 예 |
|---|---|---|
| **Container** | 영상+오디오+메타데이터를 담는 바구니 | .mp4, .mov, .avi |
| **Codec** | 압축/해제 알고리즘(화질 유지하며 크기↓) | H.264, VP9, HEVC |

### Bitrate와 ABR

- **bitrate**: 단위 시간당 처리 비트. 높을수록 고화질이나 더 많은 처리·대역폭 필요.
- 한 영상을 여러 비트레이트로 인코딩(`funny_720p.mp4`, `funny_1080p.mp4`…) → 플레이어가 네트워크 상태에 따라 세그먼트 단위로 적절한 버전을 골라 받음(adaptive bitrate streaming).

### 스트리밍 프로토콜

ABR을 실어 나르는 표준: **MPEG-DASH**, **Apple HLS**, Microsoft Smooth Streaming, Adobe HDS. 각기 지원 인코딩·플레이어가 달라 용도에 맞게 선택(이름 암기보다 선택 기준이 요점).

## 트레이드오프 & 선택 기준

- **인코딩 버전 수 vs 저장·비용**: 해상도×코덱×비트레이트 조합이 많을수록 호환성↑·UX↑이나 저장·인코딩 비용↑. long-tail 콘텐츠는 버전을 줄이거나 on-demand 인코딩.
- **codec 선택**: H.264는 호환성 최강, VP9/HEVC/AV1은 압축률↑이나 인코딩 비용·기기 지원 편차. 대상 기기 분포로 결정.
- 인코딩은 **CPU 집약·시간 소요** → 병렬 파이프라인([[dag-task-pipeline]])이 필수.

## 실무 적용 시 고려사항

- 영상을 **GOP(Group of Pictures) 청크**로 분할하면 독립 재생·병렬 인코딩·resumable 업로드가 가능 — transcoding과 업로드 최적화의 공통 단위.
- 인코딩 산출물은 [[blob-storage]]에 두고 인기작은 [[cdn]]으로 배포.
- live streaming은 동일 파이프라인이나 지연 요구가 엄격해 더 짧은 청크·다른 프로토콜.

## 다른 개념과의 관계

- [[dag-task-pipeline]] — transcoding을 단계화·병렬 실행하는 처리 모델.
- [[blob-storage]]·[[cdn]] — 인코딩 결과의 저장·배포.
- [[pre-signed-url]] — 인코딩 전 원본 업로드 경로.

## 등장 사례

- ch14 — YouTube 영상 인코딩, 다중 해상도 ABR
- Netflix/Facebook(SVE) — 대규모 분산 비디오 인코딩 파이프라인
