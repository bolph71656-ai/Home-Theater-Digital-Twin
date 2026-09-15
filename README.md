# Home Theater Digital Twin

Windows上で個人利用することを前提とした、ホームシアター環境のデジタルツイン／測定統合／可視化ツールです。

本プロジェクトは **REW (Room EQ Wizard) を置き換えるものではありません**。REWの測定・解析能力を活用しつつ、部屋形状、スピーカー配置、リスニング位置、AVR設定、測定履歴を一つのモデルに統合し、比較・診断・可視化・将来的な配置最適化を行うことを目的とします。

## 現在のフェーズ

**Planning only / 本格実装前**

まだアプリ本体の実装は開始しません。まず既存ソフトウェア・OSSを最大限再利用し、仕様・データモデル・アーキテクチャを固めます。

詳細は [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) を参照してください。

## 基本方針

- Windows-first、個人利用を優先
- ローカル完結を基本とし、クラウド前提にしない
- REWの測定・DSP機能を再実装しない
- 既存OSSを積極的に再利用する
- 3Dモデルと実測データを明確に区別する
- サブウーファーなしのホームシアターも主要ユースケースとする
- 過剰な認証、暗号化、マルチユーザー、サーバー運用は行わない

## 想定ユーザー環境

- Windows 11
- REW
- USB測定マイク
- HDMI経由でAVRへ測定信号を出力
- Yamaha RX-A4A級AVRを初期ターゲット
- 5.x.x / 7.x.x / Atmos構成、およびサブウーファーなし構成

## Status

Design / planning phase. No production implementation yet.
