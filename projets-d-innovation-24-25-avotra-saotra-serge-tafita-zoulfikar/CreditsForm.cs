using System;
using System.Drawing;
using System.Windows.Forms;

public class CreditsForm : Form
{
    public CreditsForm()
    {
        InitializeComponents();
    }

    private void InitializeComponents()
    {
        this.Size = new Size(800, 600);
        this.Text = "Credits Form";

        // Example content
        var label = new Label
        {
            Text = "Hello from CreditsForm!",
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleCenter,
            Font = new Font("Segoe UI", 16, FontStyle.Bold)
        };

        this.Controls.Add(label);
    }
}
