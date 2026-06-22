import React, { useState } from 'react';
import { SidebarItem } from './types';
import { Sidebar } from './components/Sidebar';
import { AccountManagement } from './components/AccountManagement';
import { PlaceholderPage } from './components/PlaceholderPage';
import { ToastContainer } from './components/Toast';

const App: React.FC = () => {
  const [activeItem, setActiveItem] = useState<SidebarItem>('accounts');

  const handleItemClick = (item: SidebarItem) => {
    if (item === 'logout') {
      // Simulate logout
      if (window.confirm('确定要退出登录吗？')) {
        window.location.reload();
      }
      return;
    }
    setActiveItem(item);
  };

  const renderContent = () => {
    switch (activeItem) {
      case 'accounts':
        return <AccountManagement />;
      default:
        return <PlaceholderPage item={activeItem} />;
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0d1117]">
      <Sidebar activeItem={activeItem} onItemClick={handleItemClick} />
      <main className="flex-1 overflow-hidden">
        {renderContent()}
      </main>
      <ToastContainer />
    </div>
  );
};

export default App;
