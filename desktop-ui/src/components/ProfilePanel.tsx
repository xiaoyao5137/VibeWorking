import React, { useEffect, useState } from 'react'
import { Calendar, Edit2, User } from 'lucide-react'

interface UserProfile {
  id: number
  snapshot_type: string
  snapshot_date: string
  content: {
    roles: string[]
    projects: Array<{ name: string; desc: string }>
    responsibilities: string[]
    work_style: string
    creation_style: string
  }
  is_system_generated: boolean
  created_at: string
  updated_at: string
}

type SnapshotType = 'daily' | 'weekly' | 'monthly'

const ProfilePanel: React.FC = () => {
  const [profiles, setProfiles] = useState<UserProfile[]>([])
  const [selectedType, setSelectedType] = useState<SnapshotType>('weekly')
  const [selectedProfile, setSelectedProfile] = useState<UserProfile | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState<UserProfile['content'] | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchProfiles()
  }, [selectedType])

  const fetchProfiles = async () => {
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:17070/api/profiles?type=${selectedType}&limit=20`)
      const data = await res.json()
      setProfiles(data)
      if (data.length > 0 && !selectedProfile) {
        setSelectedProfile(data[0])
      }
    } catch (err) {
      console.error('获取画像失败:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = () => {
    if (selectedProfile) {
      setEditContent(selectedProfile.content)
      setIsEditing(true)
    }
  }

  const handleSave = async () => {
    if (!selectedProfile || !editContent) return

    try {
      await fetch(`http://localhost:17070/api/profiles/${selectedProfile.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent }),
      })
      setIsEditing(false)
      fetchProfiles()
    } catch (err) {
      console.error('保存失败:', err)
    }
  }

  const handleCancel = () => {
    setIsEditing(false)
    setEditContent(null)
  }

  return (
    <div className="profile-panel" style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <User size={24} />
          用户画像
        </h1>
        <p style={{ color: '#666', fontSize: '14px' }}>
          基于时间线数据自动分析生成，帮助理解你的工作内容和创作风格
        </p>
      </div>

      {/* 时间轴选择器 */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
        {(['daily', 'weekly', 'monthly'] as SnapshotType[]).map((type) => (
          <button
            key={type}
            onClick={() => setSelectedType(type)}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: selectedType === type ? '2px solid #3b82f6' : '1px solid #e5e7eb',
              background: selectedType === type ? '#eff6ff' : 'white',
              color: selectedType === type ? '#3b82f6' : '#374151',
              cursor: 'pointer',
              fontWeight: selectedType === type ? '600' : '400',
            }}
          >
            {type === 'daily' && '每日'}
            {type === 'weekly' && '每周'}
            {type === 'monthly' && '每月'}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#666' }}>加载中...</div>
      ) : profiles.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px', color: '#666' }}>
          暂无画像数据，系统将在每日凌晨自动生成
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '24px' }}>
          {/* 左侧快照列表 */}
          <div style={{ borderRight: '1px solid #e5e7eb', paddingRight: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Calendar size={16} />
              快照版本
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {profiles.map((profile) => (
                <div
                  key={profile.id}
                  onClick={() => setSelectedProfile(profile)}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    border: selectedProfile?.id === profile.id ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                    background: selectedProfile?.id === profile.id ? '#eff6ff' : 'white',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontSize: '14px', fontWeight: '600', marginBottom: '4px' }}>
                    {profile.snapshot_date}
                  </div>
                  <div style={{ fontSize: '12px', color: '#666' }}>
                    {profile.is_system_generated ? '系统生成' : '用户编辑'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 右侧画像内容 */}
          {selectedProfile && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: '600' }}>
                  {selectedProfile.snapshot_date} 画像
                </h3>
                {!isEditing && (
                  <button
                    onClick={handleEdit}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 16px',
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                      background: 'white',
                      cursor: 'pointer',
                    }}
                  >
                    <Edit2 size={16} />
                    编辑
                  </button>
                )}
              </div>

              {isEditing && editContent ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>
                      工作角色
                    </label>
                    <input
                      type="text"
                      value={editContent.roles.join(', ')}
                      onChange={(e) => setEditContent({ ...editContent, roles: e.target.value.split(',').map(s => s.trim()) })}
                      style={{ width: '100%', padding: '8px', border: '1px solid #e5e7eb', borderRadius: '6px' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>
                      工作风格
                    </label>
                    <textarea
                      value={editContent.work_style}
                      onChange={(e) => setEditContent({ ...editContent, work_style: e.target.value })}
                      style={{ width: '100%', padding: '8px', border: '1px solid #e5e7eb', borderRadius: '6px', minHeight: '80px' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>
                      创作风格
                    </label>
                    <textarea
                      value={editContent.creation_style}
                      onChange={(e) => setEditContent({ ...editContent, creation_style: e.target.value })}
                      style={{ width: '100%', padding: '8px', border: '1px solid #e5e7eb', borderRadius: '6px', minHeight: '80px' }}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                    <button onClick={handleCancel} style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #e5e7eb', background: 'white', cursor: 'pointer' }}>
                      取消
                    </button>
                    <button onClick={handleSave} style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#3b82f6', color: 'white', cursor: 'pointer' }}>
                      保存
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#666', marginBottom: '8px' }}>工作角色</h4>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {selectedProfile.content.roles.map((role, i) => (
                        <span key={i} style={{ padding: '4px 12px', borderRadius: '16px', background: '#eff6ff', color: '#3b82f6', fontSize: '14px' }}>
                          {role}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#666', marginBottom: '8px' }}>当前项目</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {selectedProfile.content.projects.map((proj, i) => (
                        <div key={i} style={{ padding: '12px', borderRadius: '8px', background: '#f9fafb', border: '1px solid #e5e7eb' }}>
                          <div style={{ fontWeight: '600', marginBottom: '4px' }}>{proj.name}</div>
                          <div style={{ fontSize: '14px', color: '#666' }}>{proj.desc}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#666', marginBottom: '8px' }}>主要职责</h4>
                    <ul style={{ paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {selectedProfile.content.responsibilities.map((resp, i) => (
                        <li key={i} style={{ fontSize: '14px', color: '#374151' }}>{resp}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#666', marginBottom: '8px' }}>工作风格</h4>
                    <p style={{ fontSize: '14px', color: '#374151', lineHeight: '1.6' }}>
                      {selectedProfile.content.work_style}
                    </p>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#666', marginBottom: '8px' }}>创作风格</h4>
                    <p style={{ fontSize: '14px', color: '#374151', lineHeight: '1.6' }}>
                      {selectedProfile.content.creation_style}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default ProfilePanel
