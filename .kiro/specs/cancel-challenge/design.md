# Design Document: Cancel Challenge Feature

## Overview

This feature adds a "Cancel Challenge" button to the existing active fight message, allowing challengers to safely cancel their stuck challenges. The implementation focuses on minimal code changes to avoid disrupting the live game system.

## Architecture

### Component Integration
- **UI Layer**: Add cancel button to existing message in `telegram_bot.py`
- **Handler Layer**: New callback handler for cancel operations
- **Database Layer**: Use existing methods with status update to 'cancelled'
- **Notification Layer**: Reuse existing group messaging functionality

### Safety Approach
- No modification of existing game logic
- Only additive changes (new button + new handler)
- Reuse existing database methods
- Preserve all existing functionality

## Components and Interfaces

### 1. UI Component (telegram_bot.py)
**Location**: Lines 1157-1165 in `request_pvp_fight_handler`

**Current Code**:
```python
text = (
    "⚠️ **شما قبلاً چالش فعالی دارید!**\n\n"
    "لطفاً فایت فعلی را کامل کنید یا منتظر انقضای آن باشید."
)
keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]]
```

**Enhanced Code**:
```python
text = (
    "⚠️ **شما قبلاً چالش فعالی دارید!**\n\n"
    "لطفاً فایت فعلی را کامل کنید یا منتظر انقضای آن باشید."
)
keyboard = [
    [InlineKeyboardButton("❌ لغو چالش", callback_data=f"cancel_challenge_{active_fights[0]}")],
    [InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_main")]
]
```

### 2. Callback Handler
**New Method**: `cancel_challenge_handler`

**Interface**:
```python
async def cancel_challenge_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge cancellation requests"""
    # 1. Extract fight_id from callback_data
    # 2. Validate user is challenger
    # 3. Cancel fight in database
    # 4. Notify group
    # 5. Update user interface
```

### 3. Database Operations
**Existing Method**: Use `DatabaseManager.cancel_fight()` or create if needed

**Interface**:
```python
def cancel_fight(self, fight_id: str, user_id: int) -> Tuple[bool, str, Optional[int]]:
    """Cancel a fight if user is challenger
    Returns: (success, message, chat_id_for_notification)
    """
```

## Data Models

### Fight Status Update
- Current statuses: 'waiting_opponent', 'challenger_card_selected', etc.
- New status: 'cancelled'
- Preserve existing fight record for analytics

### Database Schema (No Changes)
```sql
-- Existing active_fights table remains unchanged
CREATE TABLE active_fights (
    fight_id TEXT PRIMARY KEY,
    challenger_id INTEGER NOT NULL,
    opponent_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting_opponent',
    chat_id INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Challenger-Only Cancellation
*For any* active fight and any user attempting to cancel, the cancellation should succeed if and only if the user is the original challenger of that fight.
**Validates: Requirements 2.1**

### Property 2: Fight Status Consistency
*For any* fight that is successfully cancelled, the fight status in the database should be updated to 'cancelled' and the fight should no longer appear in active fights queries.
**Validates: Requirements 5.1**

### Property 3: Immediate Challenge Availability
*For any* challenger who successfully cancels a fight, they should immediately be able to create a new challenge without waiting for the timeout period.
**Validates: Requirements 1.5**

### Property 4: Group Notification Delivery
*For any* successfully cancelled fight with a valid chat_id, a notification message should be sent to the corresponding group chat.
**Validates: Requirements 4.1**

### Property 5: Database Transaction Atomicity
*For any* cancellation operation, either all database changes succeed together (status update) or none succeed, maintaining database consistency.
**Validates: Requirements 5.2**

### Property 6: UI State Consistency
*For any* user with active fights, the cancel button should be displayed, and for any user without active fights, the cancel button should not be displayed.
**Validates: Requirements 2.4**

## Error Handling

### Validation Errors
- **Invalid User**: Return error message "شما مجاز به لغو این چالش نیستید"
- **Fight Not Found**: Return error message "چالش یافت نشد"
- **Already Cancelled**: Return error message "این چالش قبلاً لغو شده است"

### Database Errors
- **Connection Failure**: Log error, return user-friendly message
- **Transaction Failure**: Rollback changes, return error message
- **Constraint Violation**: Handle gracefully, return appropriate message

### Network Errors
- **Group Notification Failure**: Log warning, continue with user notification
- **Telegram API Failure**: Retry once, then continue without notification

## Testing Strategy

### Unit Tests
- Test cancel button display logic
- Test challenger validation
- Test database status updates
- Test error handling scenarios

### Property-Based Tests
- Generate random fight scenarios and verify challenger-only access
- Test database consistency across multiple concurrent operations
- Verify UI state consistency with various fight combinations

### Integration Tests
- Test complete cancellation flow from button press to group notification
- Test interaction with existing fight creation logic
- Test timeout and expiration edge cases

## Implementation Plan

### Phase 1: Core Functionality
1. Add cancel button to existing UI message
2. Create callback handler for cancellation
3. Implement database cancellation method
4. Add basic validation and error handling

### Phase 2: Notifications and Polish
1. Add group chat notifications
2. Implement comprehensive error messages
3. Add logging for debugging
4. Test edge cases and error scenarios

### Phase 3: Testing and Deployment
1. Test in development environment
2. Verify no impact on existing functionality
3. Deploy incrementally with monitoring
4. Monitor for any issues in production

## Risk Mitigation

### Code Safety
- Only additive changes, no modifications to existing logic
- Extensive validation before database operations
- Graceful error handling to prevent crashes

### User Experience
- Clear feedback messages for all scenarios
- Consistent UI styling with existing buttons
- Immediate response to user actions

### System Stability
- Atomic database transactions
- Proper error logging
- Fallback mechanisms for network failures