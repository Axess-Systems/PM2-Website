// DashboardLayout.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { User, Settings, Bell } from 'lucide-react';

const DashboardLayout = ({ children }) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    navigate('/login');
  };

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="container mx-auto px-4 py-3 flex justify-between items-center">
          <div className="font-semibold text-xl">Dashboard</div>
          <div className="flex items-center space-x-4">
            <Bell className="h-5 w-5 cursor-pointer" />
            <Settings className="h-5 w-5 cursor-pointer" />
            <User className="h-5 w-5" />
            <Button variant="ghost" onClick={handleLogout}>Logout</Button>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto px-4 py-8">
        {children}
      </main>

      <footer className="bg-gray-50 border-t mt-auto">
        <div className="container mx-auto px-4 py-3 text-center text-gray-600">
          © 2024 Dashboard. All rights reserved.
        </div>
      </footer>
    </div>
  );
};

export default DashboardLayout;