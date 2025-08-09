// static/game.js
document.addEventListener('DOMContentLoaded', function() {
    // 全局变量
    let currentSpellsPage = 1;
    const spellsPerPage = 9;
    
    // 初始化侧边栏
    document.querySelector('.sidebar-toggle').addEventListener('click', () => {
        document.querySelector('.sidebar').classList.toggle('collapsed');
    });
    
    // 模态框功能
    window.onclick = function(event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
        }
    };
    
    // 物品操作
    window.itemAction = function(action, item, container = '') {
        fetch('/item_action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `action=${action}&item=${encodeURIComponent(item)}&container=${container}`
        })
        .then(response => response.json())
        .then(data => {
            if (data.event_message) {
                showEventMessage(data.event_message);
            }
            if (action === 'discard' || action === 'use') {
                loadInventory();
            }
            if (container) {
                loadContainer(container);
            }
            updateStats(data.stats, data.equipment);
            document.querySelector('.undo-button').disabled = !data.can_undo;
        });
    };
    
    // 容器操作
    window.loadContainer = function(containerId) {
        fetch(`/scene_container/${containerId}`)
            .then(response => response.json())
            .then(data => {
                const trunkItems = document.getElementById('trunk-items');
                const inventoryItems = document.getElementById('inventory-items');
                trunkItems.innerHTML = '';
                inventoryItems.innerHTML = '';
                
                if (Object.keys(data.items).length === 0) {
                    trunkItems.innerHTML = '<div class="empty-message">容器是空的</div>';
                } else {
                    for (let [item, quantity] of Object.entries(data.items)) {
                        const itemDiv = createContainerItem(item, quantity, containerId);
                        trunkItems.appendChild(itemDiv);
                    }
                }
                
                if (Object.keys(data.inventory).length === 0) {
                    inventoryItems.innerHTML = '<div class="empty-message">背包是空的</div>';
                } else {
                    for (let [item, quantity] of Object.entries(data.inventory)) {
                        const itemDiv = createInventoryItem(item, quantity, containerId);
                        inventoryItems.appendChild(itemDiv);
                    }
                }
                
                updateInventoryStats(data.inventory_length);
            });
    };
    
    // 库存操作
    window.loadInventory = function() {
        fetch('/scene_container/inventory')
            .then(response => response.json())
            .then(data => {
                const inventoryContainer = document.getElementById('inventory');
                inventoryContainer.innerHTML = '';
                
                if (Object.keys(data.inventory).length === 0) {
                    inventoryContainer.innerHTML = '<div class="empty-message">背包是空的</div>';
                } else {
                    for (let [item, quantity] of Object.entries(data.inventory)) {
                        const itemDiv = createInventoryItem(item, quantity);
                        inventoryContainer.appendChild(itemDiv);
                    }
                }
                
                updateInventoryStats(data.inventory_length);
            });
    };
    
    // 咒语功能
    window.loadSpells = function(page) {
        fetch('/get_spells')
            .then(response => response.json())
            .then(data => {
                const spellsList = document.getElementById('spells-list');
                spellsList.innerHTML = '';
                const start = (page - 1) * spellsPerPage;
                const end = start + spellsPerPage;
                const paginatedSpells = data.spells.slice(start, end);
                
                if (paginatedSpells.length === 0) {
                    spellsList.innerHTML = '<div class="empty-message">你还未学会任何咒语</div>';
                } else {
                    paginatedSpells.forEach(spell => {
                        const spellDiv = createSpellItem(spell);
                        spellsList.appendChild(spellDiv);
                    });
                }
                
                updateSpellsPagination(data.spells.length, page);
            });
    };

    // 成就功能
    window.openAchievementsModal = function() {
        document.getElementById('achievementsModal').style.display = 'block';
        loadAchievements();
    };

    window.loadAchievements = function() {
        fetch('/get_achievements')
            .then(response => response.json())
            .then(data => {
                const achievementsList = document.getElementById('achievements-list');
                achievementsList.innerHTML = '';
                
                if (data.achievements.length === 0) {
                    achievementsList.innerHTML = '<div class="empty-message">你还未获得任何成就</div>';
                } else {
                    data.achievements.forEach(achievement => {
                        const achievementDiv = document.createElement('div');
                        achievementDiv.className = 'inventory-item';
                        achievementDiv.innerHTML = `
                            <div class="item-icon">🏆</div>
                            <div class="item-name">${achievement.name}</div>
                            <div class="item-description">${achievement.description}</div>`;
                        achievementsList.appendChild(achievementDiv);
                    });
                }
            });
    };

    // 辅助函数
    function createContainerItem(item, quantity, containerId) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'inventory-item';
        itemDiv.innerHTML = `
            <div class="item-icon">🎒</div>
            <div class="item-name">${item} (x${quantity})</div>
            <div class="item-actions">
                <button class="action-button" onclick="itemAction('move_to_inventory', '${item}', '${containerId}')">取出</button>
                <button class="action-button" onclick="itemAction('discard', '${item}', '${containerId}')">丢弃</button>
            </div>`;
        return itemDiv;
    }
    
    function createInventoryItem(item, quantity, containerId = '') {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'inventory-item';
        
        if (containerId) {
            itemDiv.innerHTML = `
                <div class="item-icon">🎒</div>
                <div class="item-name">${item} (x${quantity})</div>
                <div class="item-actions">
                    <button class="action-button" onclick="itemAction('move_to_container', '${item}', '${containerId}')">放入容器</button>
                </div>`;
        } else {
            itemDiv.innerHTML = `
                <div class="item-icon">🎒</div>
                <div class="item-name">${item} (x${quantity})</div>
                <div class="item-actions">
                    <button class="action-button" onclick="itemAction('use', '${item}')">使用/穿戴</button>
                    <button class="action-button" onclick="itemAction('discard', '${item}')">丢弃</button>
                </div>`;
        }
        
        return itemDiv;
    }
    
    function createSpellItem(spell) {
        const spellDiv = document.createElement('div');
        spellDiv.className = 'inventory-item';
        spellDiv.innerHTML = `
            <div class="item-icon">🪄</div>
            <div class="item-name">${spell.name}</div>
            <div class="item-description">${spell.description}</div>`;
        return spellDiv;
    }
    
    function updateInventoryStats(length) {
        const statsElement = document.querySelector('.inventory-stats');
        statsElement.innerHTML = `背包容量: <span class="${length < 8 ? 'good' : 'warning'}">${length}/10</span>`;
    }
    
    function updateSpellsPagination(totalItems, currentPage) {
        const totalPages = Math.ceil(totalItems / spellsPerPage);
        document.getElementById('spells-page-info').textContent = `第 ${currentPage} 页 / 共 ${totalPages} 页`;
        
        const prevButton = document.querySelector('.pagination-button[onclick="prevSpellsPage()"]');
        const nextButton = document.querySelector('.pagination-button[onclick="nextSpellsPage()"]');
        
        prevButton.disabled = currentPage === 1;
        nextButton.disabled = currentPage === totalPages;
    }
    
    function showEventMessage(message) {
        const eventDiv = document.createElement('div');
        eventDiv.className = 'event-message';
        eventDiv.textContent = message;
        
        const sceneTitle = document.querySelector('.scene-title');
        sceneTitle.parentNode.insertBefore(eventDiv, sceneTitle.nextSibling);
        
        setTimeout(() => eventDiv.remove(), 3000);
    }
    
    // 全局函数
    window.openModal = function(modalId) {
        document.getElementById(modalId).style.display = 'block';
        if (modalId === 'trunkModal') {
            loadContainer('trunk');
        }
    };
    
    window.closeModal = function(modalId) {
        document.getElementById(modalId).style.display = 'none';
    };
    
    window.showTab = function(tabId) {
        document.querySelectorAll('.items-container').forEach(tab => tab.style.display = 'none');
        document.getElementById(tabId).style.display = 'grid';
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        event.target.classList.add('active');
    };
    
    window.updateStats = function(stats, equipment) {
        const maxHealth = stats.max_health || 100;
        const maxSan = stats.max_san || 100;
        const maxFatigue = stats.max_fatigue || 100;
        const healthBar = document.getElementById('health-bar');
        if (healthBar) healthBar.style.width = `${(stats.health / maxHealth) * 100}%`;
        const healthNum = document.getElementById('health-number');
        if (healthNum) healthNum.textContent = `${stats.health}/${maxHealth}`;
        const sanBar = document.getElementById('san-bar');
        if (sanBar) sanBar.style.width = `${(stats.san / maxSan) * 100}%`;
        const sanNum = document.getElementById('san-number');
        if (sanNum) sanNum.textContent = `${stats.san}/${maxSan}`;
        const fatigueBar = document.getElementById('fatigue-bar');
        if (fatigueBar) fatigueBar.style.width = `${(stats.fatigue / maxFatigue) * 100}%`;
        const fatigueNum = document.getElementById('fatigue-number');
        if (fatigueNum) fatigueNum.textContent = `${stats.fatigue}/${maxFatigue}`;
        const galleons = document.getElementById('galleons-stat');
        if (galleons) galleons.textContent = `加隆: ${stats.galleons}`;
        const sickle = document.getElementById('sickle-stat');
        if (sickle) sickle.textContent = `西可: ${stats.sickle}`;
        const knut = document.getElementById('knut-stat');
        if (knut) knut.textContent = `纳特: ${stats.knut}`;
        const timeLabel = document.getElementById('time-stat');
        if (timeLabel) timeLabel.textContent = `时间: ${stats.time}`;
        document.querySelector('.inventory li:nth-child(1)').textContent = `手部: ${equipment.hand || '空'}`;
        document.querySelector('.inventory li:nth-child(2)').textContent = `身体: ${equipment.body || '空'}`;
    };
    
    window.openSpellsModal = function() {
        currentSpellsPage = 1;
        loadSpells(currentSpellsPage);
        document.getElementById('spellsModal').style.display = 'block';
    };
    
    window.prevSpellsPage = function() {
        if (currentSpellsPage > 1) {
            currentSpellsPage--;
            loadSpells(currentSpellsPage);
        }
    };
    
    window.nextSpellsPage = function() {
        fetch('/get_spells')
            .then(response => response.json())
            .then(data => {
                const totalPages = Math.ceil(data.spells.length / spellsPerPage);
                if (currentSpellsPage < totalPages) {
                    currentSpellsPage++;
                    loadSpells(currentSpellsPage);
                }
            });
    };
    
    window.restoreStats = function() {
        fetch('/restore_stats', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.message) alert(data.message);
                location.reload();
            });
    };
    
    window.gainAllSpells = function() {
        fetch('/gain_all_spells', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                showEventMessage(data.message);
                if (document.getElementById('spellsModal').style.display === 'block') {
                    loadSpells(currentSpellsPage);
                }
            });
    };

    window.openFavorModal = function() {
        document.getElementById('favorModal').style.display = 'block';
        loadFavor();
    };

    window.loadFavor = function() {
        fetch('/get_favor')
            .then(res => res.json())
            .then(data => {
                const list = document.getElementById('favor-list');
                list.innerHTML = '';
                const arr = data.favor || [];
                if (arr.length === 0) {
                    list.innerHTML = '<div class="empty-message">你还没有与任何人建立关系</div>';
                    return;
                }
                arr.forEach(entry => {
                    const div = document.createElement('div');
                    div.className = 'inventory-item';
                    div.innerHTML = `
                        <div class="item-icon">💬</div>
                        <div class="item-name">${entry.person}</div>
                        <div class="item-description">好感度：${entry.score}（关系：${entry.relation}）</div>
                    `;
                    list.appendChild(div);
                });
            });
    };

    window.undoAction = function() {
        fetch('/undo')
            .then(response => response.text())
            .then(() => location.reload());
    };
    
    // 初始化库存显示
    loadInventory();

    // 文本特效解析与应用
    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function mapColorKeyword(keyword) {
        const k = keyword.trim().toLowerCase();
        const map = {
            'red': '#ff4d4f', '蓝': '#3b82f6', '蓝色': '#3b82f6', 'blue': '#3b82f6',
            '绿': '#22c55e', '绿色': '#22c55e', 'green': '#22c55e',
            '黄': '#facc15', '黄色': '#facc15', 'yellow': '#facc15',
            '紫': '#a855f7', '紫色': '#a855f7', 'purple': '#a855f7',
            '青': '#06b6d4', '青色': '#06b6d4', 'cyan': '#06b6d4',
            '橙': '#fb923c', '橙色': '#fb923c', 'orange': '#fb923c',
            '白': '#e5e7eb', '白色': '#e5e7eb', 'white': '#e5e7eb',
            '黑': '#111827', '黑色': '#111827', 'black': '#111827',
            '金': '#d4af37', '金色': '#d4af37', 'gold': '#d4af37'
        };
        return map[k] || k || '#d4af37';
    }

    function transformTextEffects(inputHtml) {
        if (!inputHtml) return inputHtml;
        let output = inputHtml;
        // 乱码/故障：%%文本%%
        output = output.replace(/%%([\s\S]*?)%%/g, (m, text) => {
            const safe = escapeHtml(text);
            return `<span class="glitch-text" data-text="${safe}">${safe}</span>`;
        });
        // 发光颜色：&&文本#颜色#&&
        output = output.replace(/&&([\s\S]*?)#([^#]+?)#&&/g, (m, text, color) => {
            const safeText = escapeHtml(text);
            const c = mapColorKeyword(color);
            return `<span class="glow-text" style="--glow-color:${c}">${safeText}</span>`;
        });
        // 加粗：**文本**
        output = output.replace(/\*\*([\s\S]+?)\*\*/g, (m, text) => `<strong>${escapeHtml(text)}</strong>`);
        return output;
    }

    function applyTextEffects() {
        const nodes = document.querySelectorAll('.scene-description, .dialogue, .scene-title, .dialogue-choice');
        nodes.forEach(node => {
            const raw = node.textContent;
            node.innerHTML = transformTextEffects(raw);
        });
    }

    applyTextEffects();
});