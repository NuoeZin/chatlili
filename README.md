# chatlili

![Python version](https://img.shields.io/badge/python-3.6+-blue.svg)
![Flask](https://img.shields.io/badge/flask-2.0+-green.svg)
![License](https://img.shields.io/badge/license-MIT-red.svg)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/yourusername/chatlili/pulls)

[![Discord](https://img.shields.io/discord/xxxxxxxxxx?label=Discord&logo=discord&color=5865F2)](https://discord.gg/example)
[![Telegram](https://img.shields.io/badge/Telegram-join-blue?logo=telegram)](https://t.me/chatlili)
[![Twitter](https://img.shields.io/twitter/follow/chatlili?style=social)](https://twitter.com/chatlili)

**Python网页简易chat服务器分布模式大厅注册聊天厅服务包**

> 🐛 bug闷多，懒得再改了

<img src="https://via.placeholder.com/800x400/1a1a1a/ffffff?text=chatlili+Demo+Screenshot" alt="chatlili demo" width="100%"/>

## 📋 项目简介

chatlili 是一个基于Python的简易分布式聊天系统服务包。它实现了**大厅-房间**模式的分布式聊天架构，支持多服务器注册、动态房间管理以及实时消息广播。

## ✨ 核心特性

| 特性 | 描述 |
|------|------|
| 🏢 **分布式架构** | 支持多个聊天服务器注册到中心大厅 |
| 🏠 **动态房间管理** | 用户可创建、加入、离开聊天房间 |
| 🔄 **实时消息广播** | 房间内消息实时推送给所有成员 |
| 📡 **跨服务器通信** | 不同服务器上的用户可以加入同一房间 |
| 🚪 **优雅退出机制** | 支持用户主动断开连接 |

## 🚀 快速开始

### 前置要求

- Python 3.6+
- pip 包管理器

### 安装依赖

```bash
pip install flask flask-socketio requests
