# Implementation Plan: Cancel Challenge Feature

## Overview

Safe implementation of challenge cancellation feature with minimal impact on existing live system.

## Tasks

- [x] 1. Add Cancel Button to Existing UI Message
  - Modify the active fight message in `request_pvp_fight_handler` method
  - Add "❌ لغو چالش" button with proper callback_data format
  - Ensure button only appears when user has active fights
  - _Requirements: 1.1, 3.5_

- [-] 2. Create Challenge Cancellation Handler
  - [-] 2.1 Implement `cancel_challenge_handler` method in TelegramCardBot class
    - Extract fight_id from callback_data using pattern "cancel_challenge_{fight_id}"
    - Add proper error handling and validation
    - _Requirements: 1.2, 2.1_

  - [ ] 2.2 Add challenger validation logic
    - Verify user_id matches challenger_id in database
    - Return appropriate error message for unauthorized users
    - _Requirements: 2.1, 2.2_

  - [ ] 2.3 Integrate with callback query routing
    - Add handler to existing callback routing in main bot setup
    - Ensure proper pattern matching for "cancel_challenge_" prefix
    - _Requirements: 1.2_

- [ ] 3. Implement Database Cancellation Method
  - [ ] 3.1 Create or enhance `cancel_fight` method in DatabaseManager
    - Update fight status to 'cancelled' instead of deleting record
    - Return success status, message, and chat_id for notifications
    - Use atomic transactions for database consistency
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 3.2 Add fight validation in database method
    - Check fight exists and is not already completed/cancelled
    - Verify user is the challenger before allowing cancellation
    - _Requirements: 2.2, 2.3_

- [ ] 4. Add Group Chat Notifications
  - [ ] 4.1 Implement group notification logic
    - Send cancellation message to original group chat
    - Include challenger name in notification message
    - Handle cases where group chat is inaccessible
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 4.2 Create notification message format
    - Use clear and informative message: "⚠️ چالش {challenger_name} لغو شد"
    - Ensure message is consistent with existing bot messaging style
    - _Requirements: 4.5_

- [ ] 5. Add User Feedback and Error Handling
  - [ ] 5.1 Implement success feedback
    - Show success message to challenger after cancellation
    - Update UI to allow immediate new challenge creation
    - _Requirements: 3.1, 3.3_

  - [ ] 5.2 Add comprehensive error handling
    - Handle invalid user attempts with clear error messages
    - Manage database errors gracefully without crashing
    - Provide immediate feedback for all user actions
    - _Requirements: 2.1, 2.5, 3.4_

- [ ] 6. Register New Callback Handler
  - Add "cancel_challenge_" pattern to callback query handler routing
  - Ensure handler is properly registered in bot application setup
  - Test callback routing works correctly
  - _Requirements: 1.2_

- [ ] 7. Testing and Validation
  - [ ] 7.1 Test challenger-only access
    - Verify only challengers can cancel their own fights
    - Test rejection of unauthorized cancellation attempts
    - _Requirements: 2.1_

  - [ ] 7.2 Test database consistency
    - Verify fight status updates correctly to 'cancelled'
    - Test that cancelled fights don't appear in active fights queries
    - _Requirements: 5.1, 5.4_

  - [ ] 7.3 Test UI state consistency
    - Verify cancel button appears only when user has active fights
    - Test button disappears after successful cancellation
    - _Requirements: 2.4, 3.3_

- [ ] 8. Final Integration and Deployment Preparation
  - Verify no impact on existing fight creation and resolution logic
  - Test complete flow from button press to group notification
  - Ensure all error scenarios are handled gracefully
  - _Requirements: 2.3, 2.5_

## Notes

- All tasks focus on additive changes only - no modification of existing game logic
- Database operations use existing connection patterns and error handling
- UI changes maintain consistency with existing button styling
- Group notifications reuse existing messaging infrastructure
- Error handling follows existing bot patterns for user feedback