import React, { useEffect, useState } from 'react';

interface ToastProps {
  message: string;
  type?: 'success' | 'error' | 'info';
  onClose: () => void;
}

export const Toast: React.FC<ToastProps> = ({ message, type = 'success', onClose }) => {
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setExiting(true);
      setTimeout(onClose, 300);
    }, 2000);
    return () => clearTimeout(timer);
  }, [onClose]);

  const bgColor = type === 'success' ? 'bg-[#238636]' : type === 'error' ? 'bg-[#da3633]' : 'bg-[#1f6feb]';

  return (
    <div
      className={`fixed top-4 right-4 z-50 ${bgColor} text-white px-4 py-2 rounded-md shadow-lg ${
        exiting ? 'toast-exit' : 'toast-enter'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{message}</span>
      </div>
    </div>
  );
};

// Toast manager hook
let toastId = 0;
let setToastsGlobal: React.Dispatch<React.SetStateAction<Array<{ id: number; message: string; type: 'success' | 'error' | 'info' }>>>;

export const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<Array<{ id: number; message: string; type: 'success' | 'error' | 'info' }>>([]);

  setToastsGlobal = setToasts;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
        />
      ))}
    </div>
  );
};

export const showToast = (message: string, type: 'success' | 'error' | 'info' = 'success') => {
  if (setToastsGlobal) {
    const id = ++toastId;
    setToastsGlobal((prev) => [...prev, { id, message, type }]);
  }
};
