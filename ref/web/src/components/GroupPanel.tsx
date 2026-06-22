import React, { useState } from 'react';
import { EmailGroup, EmailAccount } from '../types';
import { FolderIcon, PlusIcon, EditIcon, TrashIcon, CheckIcon, XIcon } from './Icons';
import { showToast } from './Toast';

interface GroupPanelProps {
  groups: EmailGroup[];
  selectedGroupId: string | null;
  onSelectGroup: (id: string) => void;
  onAddGroup: (name: string, color: string) => void;
  onUpdateGroup: (id: string, name: string, color: string) => void;
  onDeleteGroup: (id: string) => void;
  accounts: EmailAccount[];
}

const COLORS = [
  '#238636', '#1f6feb', '#8957e5', '#da3633', '#d29922',
  '#f78166', '#3fb950', '#58a6ff', '#bc8cff', '#f85149',
  '#e3b341', '#79c0ff', '#d2a8ff', '#ffa657', '#7ee787',
];

export const GroupPanel: React.FC<GroupPanelProps> = ({
  groups,
  selectedGroupId,
  onSelectGroup,
  onAddGroup,
  onUpdateGroup,
  onDeleteGroup,
  accounts,
}) => {
  const [isAdding, setIsAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState(COLORS[0]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);

  const handleAdd = () => {
    if (!newName.trim()) {
      showToast('请输入分组名称', 'error');
      return;
    }
    onAddGroup(newName.trim(), newColor);
    setNewName('');
    setNewColor(COLORS[0]);
    setIsAdding(false);
    showToast('分组创建成功');
  };

  const handleStartEdit = (group: EmailGroup) => {
    setEditingId(group.id);
    setEditName(group.name);
    setEditColor(group.color);
  };

  const handleSaveEdit = () => {
    if (!editName.trim()) {
      showToast('请输入分组名称', 'error');
      return;
    }
    if (editingId) {
      onUpdateGroup(editingId, editName.trim(), editColor);
      showToast('分组更新成功');
    }
    setEditingId(null);
  };

  const handleDelete = (id: string) => {
    onDeleteGroup(id);
    setShowDeleteConfirm(null);
    showToast('分组已删除');
  };

  const getAccountCount = (groupId: string) => {
    return accounts.filter((a) => a.groupId === groupId).length;
  };

  return (
    <div className="w-[240px] min-w-[240px] h-full bg-[#0d1117] border-r border-[#21262d] flex flex-col">
      {/* Header */}
      <div className="px-3 py-3 border-b border-[#21262d] flex items-center justify-between">
        <h2 className="text-[#f0f6fc] font-semibold text-sm">分组</h2>
        <button
          onClick={() => setIsAdding(true)}
          className="p-1 rounded-md text-[#8b949e] hover:text-[#f0f6fc] hover:bg-[#21262d] transition-all duration-200"
          title="新建分组"
        >
          <PlusIcon size={16} />
        </button>
      </div>

      {/* Add new group */}
      {isAdding && (
        <div className="px-3 py-3 border-b border-[#21262d] animate-slide-up">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="分组名称"
            className="w-full bg-[#0d1117] border border-[#30363d] rounded-md px-2 py-1.5 text-sm text-[#f0f6fc] placeholder-[#484f58] focus:border-[#58a6ff] focus:outline-none transition-colors duration-200 mb-2"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAdd();
              if (e.key === 'Escape') setIsAdding(false);
            }}
          />
          <div className="flex flex-wrap gap-1 mb-2">
            {COLORS.map((color) => (
              <button
                key={color}
                onClick={() => setNewColor(color)}
                className={`w-5 h-5 rounded-full transition-all duration-200 ${
                  newColor === color ? 'ring-2 ring-white ring-offset-1 ring-offset-[#0d1117] scale-110' : 'hover:scale-110'
                }`}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
          <div className="flex gap-1">
            <button
              onClick={handleAdd}
              className="flex-1 px-2 py-1 bg-[#238636] text-white rounded-md text-xs hover:bg-[#2ea043] transition-colors duration-200 flex items-center justify-center gap-1"
            >
              <CheckIcon size={12} /> 确定
            </button>
            <button
              onClick={() => setIsAdding(false)}
              className="flex-1 px-2 py-1 bg-[#21262d] text-[#c9d1d9] rounded-md text-xs hover:bg-[#30363d] transition-colors duration-200 flex items-center justify-center gap-1"
            >
              <XIcon size={12} /> 取消
            </button>
          </div>
        </div>
      )}

      {/* Group list */}
      <div className="flex-1 overflow-y-auto py-1">
        {groups.map((group, index) => {
          const count = getAccountCount(group.id);
          const isSelected = selectedGroupId === group.id;
          const isEditing = editingId === group.id;

          return (
            <div
              key={group.id}
              className="animate-slide-up"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              {isEditing ? (
                <div className="px-3 py-2 mx-2 my-1 bg-[#161b22] rounded-md border border-[#30363d]">
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="w-full bg-[#0d1117] border border-[#30363d] rounded px-2 py-1 text-sm text-[#f0f6fc] focus:border-[#58a6ff] focus:outline-none mb-2"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveEdit();
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                  />
                  <div className="flex flex-wrap gap-1 mb-2">
                    {COLORS.map((color) => (
                      <button
                        key={color}
                        onClick={() => setEditColor(color)}
                        className={`w-4 h-4 rounded-full transition-all duration-200 ${
                          editColor === color ? 'ring-2 ring-white ring-offset-1 ring-offset-[#0d1117] scale-110' : 'hover:scale-110'
                        }`}
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={handleSaveEdit}
                      className="flex-1 px-2 py-0.5 bg-[#238636] text-white rounded text-xs hover:bg-[#2ea043] transition-colors"
                    >
                      保存
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="flex-1 px-2 py-0.5 bg-[#21262d] text-[#c9d1d9] rounded text-xs hover:bg-[#30363d] transition-colors"
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  onClick={() => onSelectGroup(group.id)}
                  className={`group mx-2 my-0.5 px-3 py-2.5 rounded-md cursor-pointer transition-all duration-200 flex items-center gap-2.5 ${
                    isSelected
                      ? 'bg-[#1f6feb1a] border border-[#1f6feb33]'
                      : 'hover:bg-[#161b22] border border-transparent'
                  }`}
                >
                  <div
                    className="w-4 h-4 rounded flex-shrink-0 transition-transform duration-200 group-hover:scale-110"
                    style={{ backgroundColor: group.color }}
                  >
                    <FolderIcon size={16} className="text-white/80 p-0.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[#f0f6fc] text-sm truncate">{group.name}</div>
                  </div>
                  <span
                    className="text-xs px-1.5 py-0.5 rounded-full min-w-[20px] text-center transition-all duration-200"
                    style={{
                      backgroundColor: `${group.color}20`,
                      color: group.color,
                    }}
                  >
                    {count}
                  </span>
                  {/* Action buttons */}
                  <div className="hidden group-hover:flex items-center gap-0.5">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStartEdit(group);
                      }}
                      className="p-1 rounded text-[#8b949e] hover:text-[#f0f6fc] hover:bg-[#30363d] transition-all"
                    >
                      <EditIcon size={12} />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowDeleteConfirm(group.id);
                      }}
                      className="p-1 rounded text-[#8b949e] hover:text-[#f85149] hover:bg-[#da363320] transition-all"
                    >
                      <TrashIcon size={12} />
                    </button>
                  </div>
                </div>
              )}

              {/* Delete confirmation */}
              {showDeleteConfirm === group.id && (
                <div className="mx-2 my-1 p-2 bg-[#da363315] border border-[#da363340] rounded-md animate-scale-in">
                  <p className="text-[#f85149] text-xs mb-2">确认删除此分组？</p>
                  <div className="flex gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(group.id);
                      }}
                      className="flex-1 px-2 py-0.5 bg-[#da3633] text-white rounded text-xs hover:bg-[#f85149] transition-colors"
                    >
                      删除
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowDeleteConfirm(null);
                      }}
                      className="flex-1 px-2 py-0.5 bg-[#21262d] text-[#c9d1d9] rounded text-xs hover:bg-[#30363d] transition-colors"
                    >
                      取消
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {groups.length === 0 && !isAdding && (
          <div className="px-4 py-8 text-center text-[#484f58] text-sm animate-fade-in">
            <FolderIcon size={32} className="mx-auto mb-2 text-[#30363d]" />
            <p>暂无分组</p>
            <p className="text-xs mt-1">点击 + 创建新分组</p>
          </div>
        )}
      </div>
    </div>
  );
};
