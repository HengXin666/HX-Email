import React from 'react'
import { Modal, Button } from './Primitives'

interface ConfirmModalProps {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  open,
  title,
  message,
  confirmLabel = '确认',
  danger = true,
  loading,
  onConfirm,
  onCancel
}) => (
  <Modal
    open={open}
    onClose={onCancel}
    title={title}
    size="sm"
    footer={
      <>
        <Button variant="ghost" onClick={onCancel} disabled={loading}>
          取消
        </Button>
        <Button
          variant={danger ? 'danger' : 'primary'}
          onClick={onConfirm}
          loading={loading}
        >
          {confirmLabel}
        </Button>
      </>
    }
  >
    <p className="text-sm text-gh-text-secondary">{message}</p>
  </Modal>
)
