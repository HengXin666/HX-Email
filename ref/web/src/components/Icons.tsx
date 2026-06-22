import React from 'react';

interface IconProps {
  className?: string;
  size?: number;
}

export const OverviewIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M0 1.75A.75.75 0 0 1 .75 1h4.253c1.227 0 2.317.59 3 1.501A3.744 3.744 0 0 1 11.006 1h4.245a.75.75 0 0 1 .75.75v10.5a.75.75 0 0 1-.75.75h-4.507a2.25 2.25 0 0 0-1.591.659l-.622.621a.75.75 0 0 1-1.06 0l-.622-.621A2.25 2.25 0 0 0 5.258 13H.75a.75.75 0 0 1-.75-.75Zm7.251 10.324.004-5.073-.002-2.253A2.25 2.25 0 0 0 5.003 2.5H1.5v9h3.757a3.75 3.75 0 0 1 1.994.574ZM8.755 4.75l-.004 7.322a3.75 3.75 0 0 1 1.992-.572H14.5v-9h-3.495a2.25 2.25 0 0 0-2.25 2.25Z" />
  </svg>
);

export const AccountsIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M1.5 1a.5.5 0 0 0-.5.5v13a.5.5 0 0 0 .5.5h13a.5.5 0 0 0 .5-.5v-13a.5.5 0 0 0-.5-.5h-13ZM1 1.5A1.5 1.5 0 0 1 2.5 0h13A1.5 1.5 0 0 1 17 1.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 1 14.5v-13Zm6.5 3a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0ZM6 6.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Zm-1.5 3a.5.5 0 0 0-.5.5c0 1.047.392 1.955 1.082 2.594C5.765 13.228 6.827 13.5 8 13.5c1.173 0 2.235-.272 2.918-.906A3.426 3.426 0 0 0 12 10a.5.5 0 0 0-.5-.5h-7ZM5.08 10H8 10.92c-.116.592-.39 1.08-.795 1.444-.497.447-1.196.756-2.125.756-.929 0-1.628-.309-2.125-.756A2.427 2.427 0 0 1 5.08 10Z" />
    <path d="M6.5 1.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0Zm-1 0a.5.5 0 1 0-1 0 .5.5 0 0 0 1 0Z" />
  </svg>
);

export const PlatformsIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v12.5A1.75 1.75 0 0 1 14.25 16H1.75A1.75 1.75 0 0 1 0 14.25ZM6.5 6.5v8h7.75a.25.25 0 0 0 .25-.25V6.5Zm8-1.5V1.75a.25.25 0 0 0-.25-.25H1.75a.25.25 0 0 0-.25.25V5Zm-8 10H1.75a.25.25 0 0 1-.25-.25V6.5H5.5Z" />
  </svg>
);

export const TempMailIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M0 4a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2Zm2-1a1 1 0 0 0-1 1v.217l7 4.2 7-4.2V4a1 1 0 0 0-1-1Zm13 2.383-4.708 2.825L15 11.105Zm-.034 6.876-5.64-3.471L8 9.583l-1.326-.795-5.64 3.47A1 1 0 0 0 2 13h12a1 1 0 0 0 .966-.741ZM1 11.105l4.708-2.897L1 5.383Z" />
  </svg>
);

export const ApiIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M1.5 1a.5.5 0 0 1 .5.5v13a.5.5 0 0 1-1 0v-13a.5.5 0 0 1 .5-.5Zm13 0a.5.5 0 0 1 .5.5v13a.5.5 0 0 1-1 0v-13a.5.5 0 0 1 .5-.5ZM5 4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4Zm1 0v8h4V4H6Z" />
  </svg>
);

export const SettingsIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492ZM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0Z" />
    <path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.901 3.434 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.893 3.434-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.893-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319Zm-2.633.283c.246-.835 1.428-.835 1.674 0l.094.319a1.873 1.873 0 0 0 2.693 1.115l.291-.16c.764-.415 1.6.42 1.184 1.185l-.159.292a1.873 1.873 0 0 0 1.116 2.692l.318.094c.835.246.835 1.428 0 1.674l-.319.094a1.873 1.873 0 0 0-1.115 2.693l.16.291c.415.764-.42 1.6-1.185 1.184l-.291-.159a1.873 1.873 0 0 0-2.693 1.116l-.094.318c-.246.835-1.428.835-1.674 0l-.094-.319a1.873 1.873 0 0 0-2.692-1.115l-.292.16c-.764.415-1.6-.42-1.184-1.185l.159-.291A1.873 1.873 0 0 0 1.945 8.93l-.319-.094c-.835-.246-.835-1.428 0-1.674l.319-.094A1.873 1.873 0 0 0 3.06 4.377l-.16-.292c-.415-.764.42-1.6 1.185-1.184l.292.159a1.873 1.873 0 0 0 2.692-1.115l.094-.319Z" />
  </svg>
);

export const LogoutIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M2 2.75C2 1.784 2.784 1 3.75 1h2.5a.75.75 0 0 1 0 1.5h-2.5a.25.25 0 0 0-.25.25v10.5c0 .138.112.25.25.25h2.5a.75.75 0 0 1 0 1.5h-2.5A1.75 1.75 0 0 1 2 13.25Zm6.56 9.53a.75.75 0 1 0 1.06 1.06l3.25-3.25a.75.75 0 0 0 0-1.06L9.56 5.78a.75.75 0 0 0-1.06 1.06L10.44 8.5H5.75a.75.75 0 0 0 0 1.5h4.69Z" />
  </svg>
);

export const GithubIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
  </svg>
);

export const FolderIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M1.75 1A1.75 1.75 0 0 0 0 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0 0 16 13.25v-8.5A1.75 1.75 0 0 0 14.25 3H7.5a.25.25 0 0 1-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1Z" />
  </svg>
);

export const PlusIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M8 2a.75.75 0 0 1 .75.75v4.5h4.5a.75.75 0 0 1 0 1.5h-4.5v4.5a.75.75 0 0 1-1.5 0v-4.5h-4.5a.75.75 0 0 1 0-1.5h4.5v-4.5A.75.75 0 0 1 8 2Z" />
  </svg>
);

export const TrashIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M11 1.75v-1h-6v1h-3.5a.75.75 0 0 0 0 1.5h.646l.854 10.306A1.75 1.75 0 0 0 4.748 15h6.504a1.75 1.75 0 0 0 1.748-1.694l.854-10.306h.646a.75.75 0 0 0 0-1.5H11Zm-4.5 0h3v1h-3v-1Zm4.966 1.5-.749 9H5.283l-.75-9h8.933ZM6.5 6.75v4.5a.75.75 0 0 0 1.5 0v-4.5a.75.75 0 0 0-1.5 0Zm3 0v4.5a.75.75 0 0 0 1.5 0v-4.5a.75.75 0 0 0-1.5 0Z" />
  </svg>
);

export const EditIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 0 1-.927-.928l.929-3.25c.081-.286.235-.547.445-.758l8.61-8.61Zm1.414 1.06a.25.25 0 0 0-.354 0L3.463 11.1a.25.25 0 0 0-.064.108l-.593 2.075 2.075-.593a.25.25 0 0 0 .108-.064l8.61-8.61a.25.25 0 0 0 0-.353Z" />
  </svg>
);

export const CopyIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z" />
    <path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z" />
  </svg>
);

export const MailIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M0 4a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2Zm2-1a1 1 0 0 0-1 1v.217l7 4.2 7-4.2V4a1 1 0 0 0-1-1Zm13 2.383-4.708 2.825L15 11.105Zm-.034 6.876-5.64-3.471L8 9.583l-1.326-.795-5.64 3.47A1 1 0 0 0 2 13h12a1 1 0 0 0 .966-.741ZM1 11.105l4.708-2.897L1 5.383Z" />
  </svg>
);

export const KeyIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M6.5 2a4.5 4.5 0 0 1 4.285 3.143l.003.01.01.032A4.502 4.502 0 0 1 9.5 14.5H6.5a4.5 4.5 0 0 1 0-9h.047A4.486 4.486 0 0 1 6.5 2Zm0 4.5a3 3 0 1 0 0 6h3a3 3 0 1 0 0-6h-3Z" />
  </svg>
);

export const CheckIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z" />
  </svg>
);

export const XIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l3.22 3.22a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-3.22 3.22a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z" />
  </svg>
);

export const StarIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Zm0 2.445L6.615 5.5a.75.75 0 0 1-.564.41l-3.097.45 2.24 2.184a.75.75 0 0 1 .216.664l-.528 3.084 2.769-1.456a.75.75 0 0 1 .698 0l2.77 1.456-.53-3.084a.75.75 0 0 1 .216-.664l2.24-2.183-3.096-.45a.75.75 0 0 1-.564-.41L8 2.694Z" />
  </svg>
);

export const ChevronRightIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z" />
  </svg>
);

export const EllipsisIcon: React.FC<IconProps> = ({ className = '', size = 20 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 16 16" fill="currentColor">
    <path d="M8 2a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Zm0 4.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Zm0 4.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z" />
  </svg>
);
