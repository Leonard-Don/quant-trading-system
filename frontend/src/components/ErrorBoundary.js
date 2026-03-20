import React from 'react';
import { Alert, Card, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({
      error: error,
      errorInfo: errorInfo
    });
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <Card style={{ margin: '20px' }}>
          <Alert
            message="系统错误"
            description="抱歉，系统遇到了一个错误。请尝试刷新页面。"
            type="error"
            showIcon
            action={
              <Button 
                size="small" 
                icon={<ReloadOutlined />} 
                onClick={this.handleReload}
              >
                刷新页面
              </Button>
            }
          />
          {process.env.NODE_ENV === 'development' && (
            <details style={{ marginTop: '16px', whiteSpace: 'pre-wrap' }}>
              <summary>错误详情（开发模式）</summary>
              {this.state.error && this.state.error.toString()}
              <br />
              {this.state.errorInfo?.componentStack || '组件堆栈不可用'}
            </details>
          )}
        </Card>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
