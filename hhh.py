<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>霍格沃茨冒险</title>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    <script src="{{ url_for('static', filename='game.js') }}"></script>
</head>
<body>
    <div class="game-container">
        <button class="sidebar-toggle">≡</button>
        <div class="sidebar">
            <div class="sidebar-header">
                <h2>巫师状态</h2>
            </div>
            <div class="stats">
                <div class="stat">
                    <span class="stat-label">姓名: {{ character.name }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">性别: {{ character.gender }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label" id="house-label">学院: {{ character.house or '未分院' }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">年级: {{ game_state.grade }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">生命值:</span>
                    <div class="stat-bar">
                        <div class="stat-value" style="width: {{ stats.health }}%"></div>
                    </div>
                    <span class="stat-number">{{ stats.health }}/100</span>
                </div>
                <div class="stat">
                    <span class="stat-label">理智值:</span>
                    <div class="stat-bar">
                        <div class="stat-value" style="width: {{ stats.san }}%"></div>
                    </div>
                    <span class="stat-number">{{ stats.san }}/100</span>
                </div>
                <div class="stat">
                    <span class="stat-label">疲劳值:</span>
                    <div class="stat-bar">
                        <div class="stat-value" style="width: {{ stats.fatigue }}%"></div>
                    </div>
                    <span class="stat-number">{{ stats.fatigue }}/100</span>
                </div>
                <div class="stat">
                    <span class="stat-label">加隆: {{ stats.galleons }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">西可: {{ stats.sickle }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">纳特: {{ stats.knut }}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">时间: {{ stats.time }}</span>
                </div>
            </div>
            <div class="inventory-section">
                <h3>装备</h3>
                <ul class="inventory">
                    <li>手部: {% if equipment.hand %}{{ equipment.hand }}{% else %}空{% endif %}</li>
                    <li>身体: {% if equipment.body %}{{ equipment.body }}{% else %}空{% endif %}</li>
                </ul>
            </div>
            <div class="inventory-section">
                <button class="inventory-button" onclick="openModal('inventoryModal')">🎒 查看物品</button>
                <button class="spells-button" onclick="openSpellsModal()">📜 查看所学咒语</button>
                <button class="achievements-button" onclick="openAchievementsModal()">🏆 查看成就</button>
            </div>
            {% if debug_mode %}
            <div class="sidebar-section">
                <h3>开发者快速旅行</h3>
                <ul class="locations">
                    {% for scene_id in all_scene_ids %}
                    <li><a href="{{ url_for('navigate', scene_id=scene_id) }}">{{ scene_id }}</a></li>
                    {% endfor %}
                </ul>
                <div class="dev-tools">
                    <a href="{{ url_for('reload_scenes') }}" class="dev-button">🔄 重新加载场景</a>
                    <button class="dev-button" onclick="gainAllSpells()">🪄 获得所有咒语</button>
                    <button class="dev-button" onclick="restoreStats()">🩺 恢复状态</button>
                </div>
            </div>
            {% endif %}
        </div>
        <div class="main-content">
            <div class="header-buttons">
                {% if can_undo %}
                <button class="undo-button" onclick="undoAction()">回退</button>
                {% else %}
                <button class="undo-button" disabled>回退</button>
                {% endif %}
            </div>
            <h1 class="scene-title">{{ scene.title }}</h1>
            {% if event_message %}
            <div class="event-message">{{ event_message }}</div>
            {% endif %}
            <div class="scene-description">{{ scene.description }}</div>
            {% if scene.image %}
            <div class="scene-image">
                <img src="{{ url_for('static', filename='images/' + scene.image) }}" alt="场景图片">
            </div>
            {% endif %}
            {% if is_gryffindor_dorm %}
            <div class="container-section">
                <button class="container-button" onclick="openModal('trunkModal')">📦 检查行李箱</button>
            </div>
            {% endif %}
            <div class="choices">
                {% if is_talk %}
                {% for dialogue in current_talk_node %}
                    {% if dialogue.people %}
                    <div class="dialogue">{{ dialogue.people }}: {{ dialogue.chat }}</div>
                    {% elif dialogue.chat %}
                    <div class="dialogue">{{ dialogue.chat }}</div>
                    {% endif %}
                    {% if dialogue.type == 'choice' %}
                    <div class="dialogue">{{ dialogue.question }}</div>
                    <form method="post" action="{{ url_for('talk_choose') }}">
                        {% for choice in dialogue.choices %}
                        <button type="submit" name="choice" value="{{ loop.index0 }}" class="choice-button">
                            {{ choice.text }}
                            {% if choice.effect %}
                            <span class="time-cost">疲劳+{{ choice.effect.fatigue if choice.effect.fatigue else 0 }}</span>
                            {% endif %}
                        </button>
                        {% endfor %}
                    </form>
                    {% endif %}
                {% endfor %}
                {% else %}
                <form method="post" action="{{ url_for('choose') }}">
                    {% for choice in scene.choices %}
                    <button type="submit" name="choice" value="{{ loop.index0 }}" class="choice-button">
                        {{ choice.text }}
                        {% if choice.time %}
                        <span class="time-cost">{{ choice.time }}分钟</span>
                        {% endif %}
                    </button>
                    {% endfor %}
                </form>
                {% endif %}
            </div>
        </div>
    </div>
    <div id="inventoryModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('inventoryModal')">&times;</span>
            <h2>你的物品</h2>
            <div class="items-container" id="inventory">
                {% if inventory %}
                {% for item, quantity in inventory.items() %}
                <div class="inventory-item">
                    <div class="item-icon">🎒</div>
                    <div class="item-name">{{ item }} (x{{ quantity }})</div>
                    <div class="item-actions">
                        <button class="action-button" onclick="itemAction('use', '{{ item }}')">使用/穿戴</button>
                        <button class="action-button" onclick="itemAction('discard', '{{ item }}')">丢弃</button>
                    </div>
                </div>
                {% endfor %}
                {% else %}
                <div class="empty-message">背包是空的</div>
                {% endif %}
            </div>
            <div class="inventory-stats">
                背包容量: {{ inventory.values()|sum if inventory else 0 }}/10
            </div>
        </div>
    </div>
    <div id="trunkModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('trunkModal')">&times;</span>
            <h2>管理容器</h2>
            <div class="container-tabs">
                <button class="tab-button active" onclick="showTab('trunk-items')">容器中的物品</button>
                <button class="tab-button" onclick="showTab('inventory-items')">背包物品</button>
            </div>
            <div class="items-container" id="trunk-items" style="display: grid;"></div>
            <div class="items-container" id="inventory-items" style="display: none;"></div>
            <div class="modal-footer">
                <button class="modal-close-button" onclick="closeModal('trunkModal')">关闭</button>
            </div>
        </div>
    </div>
    <div id="spellsModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('spellsModal')">&times;</span>
            <h2>所学咒语</h2>
            <div class="items-container" id="spells-list"></div>
            <div class="pagination">
                <button class="pagination-button" onclick="prevSpellsPage()">上一页</button>
                <span id="spells-page-info"></span>
                <button class="pagination-button" onclick="nextSpellsPage()">下一页</button>
            </div>
            <div class="modal-footer">
                <button class="modal-close-button" onclick="closeModal('spellsModal')">关闭</button>
            </div>
        </div>
    </div>
    <div id="achievementsModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('achievementsModal')">&times;</span>
            <h2>已获得的成就</h2>
            <div class="items-container" id="achievements-list">
                <div class="empty-message">加载中...</div>
            </div>
            <div class="modal-footer">
                <button class="modal-close-button" onclick="closeModal('achievementsModal')">关闭</button>
            </div>
        </div>
    </div>
</body>
</html>